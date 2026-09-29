let contextImage = null;
let contextPoint = null;
let contextImageUrl = "";
let activeImage = null;
let activeSourceUrl = "";
let translatedDataUrl = "";
let toolbar = null;
const responsiveSources = new WeakMap();

document.addEventListener("contextmenu", (event) => {
  contextImage = findImageFromTarget(event.target);
  contextPoint = { x: event.clientX, y: event.clientY };
  contextImageUrl = contextImage ? originalUrlFor(contextImage) : "";
}, true);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message?.type?.startsWith("image-translation-")) return;
  const image = resolveTargetImage(message);
  if (!image) {
    showToast("未找到刚才选择的图片", true);
    sendResponse({ applied: false, reason: "target-not-found" });
    return;
  }

  if (message.type === "image-translation-started") {
    activeImage = image;
    activeSourceUrl = originalUrlFor(image);
    translatedDataUrl = "";
    image.dataset.imageTranslatorRequestId = message.requestId;
    image.dataset.imageTranslatorOriginalSrc = image.getAttribute("src") || "";
    image.dataset.imageTranslatorOriginalSrcset = image.getAttribute("srcset") || "";
    responsiveSources.set(image, [...(image.closest("picture")?.querySelectorAll("source") || [])].map(
      (source) => ({ source, srcset: source.getAttribute("srcset") })
    ));
    image.dataset.imageTranslatorState = "loading";
    showToolbar(image, "正在识别并翻译...", true);
    sendResponse({ applied: true });
    return;
  }

  if (message.type === "image-translation-error") {
    delete image.dataset.imageTranslatorState;
    showToolbar(image, message.error || "翻译失败", false, true);
    sendResponse({ applied: true });
    return;
  }

  if (message.type === "image-translation-complete") {
    activeImage = image;
    activeSourceUrl = originalUrlFor(image);
    translatedDataUrl = message.translatedDataUrl;
    image.dataset.imageTranslatorOriginal = activeSourceUrl;
    image.dataset.imageTranslatorState = "translated";
    showTranslatedImage(image);
    const details = `${message.regionCount} 处文字 · ${formatElapsed(message.elapsedMs)}`;
    showToolbar(image, details, false);
    sendResponse({ applied: true });
  }
});

window.addEventListener("scroll", positionToolbar, { passive: true });
window.addEventListener("resize", positionToolbar, { passive: true });

function resolveTargetImage(message) {
  if (message.type === "image-translation-started" && contextImage?.isConnected) {
    return contextImage;
  }
  const requested = [...document.images].find((image) => {
    return image.dataset.imageTranslatorRequestId === message.requestId;
  });
  if (requested) return requested;
  const matched = [...document.images].find((image) => {
    return sameImageUrl(image.currentSrc || image.src, message.sourceUrl);
  });
  if (matched) return matched;

  if (contextImage?.isConnected && contextImageUrl && sameImageUrl(contextImageUrl, message.sourceUrl)) {
    return contextImage;
  }

  if (contextPoint) {
    const nearest = [...document.images]
      .map((image) => ({ image, distance: distanceToPoint(image, contextPoint) }))
      .sort((left, right) => left.distance - right.distance)[0];
    if (nearest && nearest.distance < 180) return nearest.image;
  }

  // Chromium's native image preview can normalize the image URL differently
  // from the context-menu URL. Use the sole image only when the preview
  // document itself points at the requested URL.
  if (document.images.length === 1 && sameImageUrl(location.href, message.sourceUrl)) {
    return document.images[0];
  }
  return null;
}

function findImageFromTarget(target) {
  if (target instanceof HTMLImageElement) return target;
  if (!(target instanceof Element)) return null;
  const pictureImage = target.closest("picture")?.querySelector("img");
  if (pictureImage) return pictureImage;
  const container = target.closest("[data-image], [role='img'], figure");
  return container?.querySelector("img") || null;
}

function distanceToPoint(image, point) {
  const rect = image.getBoundingClientRect();
  const x = Math.max(rect.left, Math.min(point.x, rect.right));
  const y = Math.max(rect.top, Math.min(point.y, rect.bottom));
  return Math.hypot(x - point.x, y - point.y);
}

function sameImageUrl(left, right) {
  if (!left || !right) return false;
  try {
    const normalize = (value) => {
      const url = new URL(value, location.href);
      url.hash = "";
      return url.href;
    };
    return normalize(left) === normalize(right);
  } catch (_) {
    return left === right;
  }
}

function originalUrlFor(image) {
  return image.dataset.imageTranslatorOriginal || image.currentSrc || image.src;
}

function showToolbar(image, status, loading, failed = false) {
  if (!toolbar) toolbar = createToolbar();
  activeImage = image;
  toolbar.querySelector("[data-role=status]").textContent = status;
  toolbar.dataset.loading = String(loading);
  toolbar.dataset.failed = String(failed);
  toolbar.hidden = false;
  positionToolbar();
}

function createToolbar() {
  const element = document.createElement("div");
  element.className = "image-translator-toolbar";
  element.hidden = true;
  element.innerHTML = `
    <span class="image-translator-spinner" aria-hidden="true"></span>
    <span class="image-translator-status" data-role="status"></span>
    <span class="image-translator-actions">
      <button type="button" data-action="original">原图</button>
      <button type="button" data-action="translated">译图</button>
      <button type="button" data-action="download" title="下载译图">下载</button>
      <button type="button" data-action="close" title="关闭">关闭</button>
    </span>`;
  element.addEventListener("click", handleToolbarAction);
  document.documentElement.appendChild(element);
  return element;
}

function handleToolbarAction(event) {
  const action = event.target.closest("button")?.dataset.action;
  if (!action || !activeImage) return;
  if (action === "original") showOriginalImage(activeImage);
  if (action === "translated" && translatedDataUrl) showTranslatedImage(activeImage);
  if (action === "download" && translatedDataUrl) downloadTranslation();
  if (action === "close") toolbar.hidden = true;
}

function showTranslatedImage(image) {
  for (const entry of responsiveSources.get(image) || []) {
    entry.source.removeAttribute("srcset");
  }
  image.removeAttribute("srcset");
  image.src = translatedDataUrl;
}

function showOriginalImage(image) {
  const originalSrc = image.dataset.imageTranslatorOriginalSrc || activeSourceUrl;
  const originalSrcset = image.dataset.imageTranslatorOriginalSrcset;
  image.src = originalSrc;
  if (originalSrcset) image.setAttribute("srcset", originalSrcset);
  for (const entry of responsiveSources.get(image) || []) {
    if (entry.srcset) entry.source.setAttribute("srcset", entry.srcset);
  }
}

function downloadTranslation() {
  const link = document.createElement("a");
  link.href = translatedDataUrl;
  link.download = `translated-image-${Date.now()}.png`;
  link.click();
}

function positionToolbar() {
  if (!toolbar || toolbar.hidden || !activeImage?.isConnected) return;
  const rect = activeImage.getBoundingClientRect();
  toolbar.style.left = `${Math.max(8, Math.min(window.innerWidth - toolbar.offsetWidth - 8, rect.left))}px`;
  const below = rect.bottom + 8;
  const top = below + toolbar.offsetHeight <= window.innerHeight
    ? below
    : Math.max(8, rect.top - toolbar.offsetHeight - 8);
  toolbar.style.top = `${top}px`;
}

function formatElapsed(value) {
  const milliseconds = Number(value) || 0;
  return milliseconds >= 1000 ? `${(milliseconds / 1000).toFixed(1)} 秒` : `${milliseconds} 毫秒`;
}

function showToast(text, failed) {
  const toast = document.createElement("div");
  toast.className = `image-translator-toast${failed ? " is-error" : ""}`;
  toast.textContent = text;
  document.documentElement.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}
