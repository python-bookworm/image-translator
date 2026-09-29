const MENU_ID = "translate-image-locally";
const DEFAULTS = {
  apiBaseUrl: "http://127.0.0.1:8080",
  sourceLanguage: "en",
  targetLanguage: "zh"
};
const MAX_INLINE_RESULT_BYTES = 25 * 1024 * 1024;

chrome.runtime.onInstalled.addListener(async () => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "翻译此图片",
    contexts: ["image"]
  });
  const existing = await chrome.storage.sync.get(Object.keys(DEFAULTS));
  await chrome.storage.sync.set({ ...DEFAULTS, ...existing });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  console.info("Context menu clicked", {
    menuItemId: info.menuItemId,
    srcUrl: info.srcUrl,
    pageUrl: info.pageUrl,
    tabId: tab?.id,
    tabUrl: tab?.url,
    mediaType: info.mediaType
  });
  if (info.menuItemId !== MENU_ID || !tab?.id) return;
  if (!info.srcUrl) {
    openErrorResult("没有获取到图片地址，请在图片本体上右键后重试").catch((error) => {
      console.error("Failed to open missing-image error page", error);
    });
    return;
  }
  const requestId = crypto.randomUUID();
  const operation = isDirectImagePreview(tab, info.srcUrl)
    ? translateDirectPreviewImage(info.srcUrl, tab, requestId)
    : translateImage(info.srcUrl, tab.id, requestId);
  operation.catch((error) => {
    console.error("Image translation failed", error);
    if (isMissingContentScript(error)) {
      const fallback = isHttpUrl(info.srcUrl)
        ? translateDirectPreviewImage(info.srcUrl, tab, requestId)
        : translatePreviewTab(tab, requestId);
      fallback.catch((previewError) => {
        console.error("Browser preview translation failed", previewError);
        return openErrorResult(previewError.message || String(previewError)).catch((resultError) => {
          console.error("Failed to open extension error page", resultError);
        });
      });
      return;
    }
    sendToTab(tab.id, {
      type: "image-translation-error",
      requestId,
      sourceUrl: info.srcUrl,
      error: error.message || String(error)
    }).catch((messageError) => console.error("Failed to report translation error", messageError));
  });
});

function isDirectImagePreview(tab, sourceUrl) {
  if (!tab.url || !sourceUrl) return false;
  try {
    const normalize = (value) => {
      const url = new URL(value);
      url.hash = "";
      return url.href;
    };
    return normalize(tab.url) === normalize(sourceUrl);
  } catch (_) {
    return false;
  }
}

async function translateImage(sourceUrl, tabId, requestId) {
  console.info(`[${requestId}] Image translation started`, { sourceUrl, tabId });
  const started = await sendToTab(tabId, { type: "image-translation-started", requestId, sourceUrl });
  if (started?.applied === false) {
    throw new Error("当前页面未找到目标图片");
  }
  const settings = await chrome.storage.sync.get(DEFAULTS);
  const apiBaseUrl = settings.apiBaseUrl.replace(/\/+$/, "");
  const imageResponse = await fetch(sourceUrl, { credentials: "include" });
  if (!imageResponse.ok) {
    throw new Error(`无法读取图片（HTTP ${imageResponse.status}）`);
  }

  const sourceBlob = await imageResponse.blob();
  console.info(`[${requestId}] Image fetched successfully`, {
    sourceUrl,
    bytes: sourceBlob.size,
    contentType: sourceBlob.type
  });
  const result = await requestTranslation(
    apiBaseUrl,
    settings,
    sourceBlob,
    fileNameFor(sourceUrl, sourceBlob.type),
    sourceUrl
  );
  const translatedBlob = result.translatedBlob;
  if (translatedBlob.size > MAX_INLINE_RESULT_BYTES) {
    throw new Error("翻译结果超过 25 MB，暂时无法在当前页面内显示");
  }
  const translatedDataUrl = await blobToDataUrl(translatedBlob);
  let applied;
  try {
    applied = await sendToTab(tabId, {
      type: "image-translation-complete",
      requestId,
      sourceUrl,
      translatedDataUrl,
      sourceLanguage: result.sourceLanguage,
      targetLanguage: settings.targetLanguage,
      regionCount: result.regionCount,
      elapsedMs: result.elapsedMs
    });
  } catch (error) {
    console.warn(`[${requestId}] Page disappeared before translated image could be applied`, error);
    applied = { applied: false, reason: "page-unavailable" };
  }
  if (applied?.applied !== true) {
    await savePreviewResult({ id: tabId }, requestId, sourceBlob, result, settings, sourceUrl);
  }
  console.info(`[${requestId}] Image translation completed`, {
    sourceUrl,
    translatedBytes: translatedBlob.size,
    regionCount: result.regionCount,
    elapsedMs: result.elapsedMs
  });
}

async function translatePreviewTab(tab, requestId) {
  const settings = await chrome.storage.sync.get(DEFAULTS);
  const apiBaseUrl = settings.apiBaseUrl.replace(/\/+$/, "");
  let screenshotDataUrl;
  try {
    screenshotDataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
  } catch (error) {
    throw new Error(`浏览器预览页无法截图，可能受到浏览器安全策略限制：${error.message || error}`);
  }
  const sourceBlob = dataUrlToBlob(screenshotDataUrl);
  const result = await requestTranslation(
    apiBaseUrl,
    settings,
    sourceBlob,
    "browser-preview.png",
    tab.url || "<browser preview screenshot>"
  );
  await savePreviewResult(tab, requestId, sourceBlob, result, settings, sourceUrl);
}

async function translateDirectPreviewImage(sourceUrl, tab, requestId) {
  console.info(`[${requestId}] Direct preview translation started`, { sourceUrl, tabId: tab.id });
  const settings = await chrome.storage.sync.get(DEFAULTS);
  const apiBaseUrl = settings.apiBaseUrl.replace(/\/+$/, "");
  const imageResponse = await fetch(sourceUrl, { credentials: "include" });
  if (!imageResponse.ok) {
    throw new Error(`无法读取预览附件（HTTP ${imageResponse.status}）`);
  }
  const sourceBlob = await imageResponse.blob();
  console.info(`[${requestId}] Direct preview image fetched successfully`, {
    sourceUrl,
    bytes: sourceBlob.size,
    contentType: sourceBlob.type
  });
  const result = await requestTranslation(
    apiBaseUrl,
    settings,
    sourceBlob,
    fileNameFor(sourceUrl, sourceBlob.type),
    sourceUrl
  );
  await savePreviewResult(tab, requestId, sourceBlob, result, settings);
}

async function savePreviewResult(tab, requestId, sourceBlob, result, settings, sourceUrl = "") {
  const id = crypto.randomUUID();
  await putResult({
    id,
    sourceBlob,
    translatedBlob: result.translatedBlob,
    sourceLanguage: result.sourceLanguage,
    targetLanguage: settings.targetLanguage,
    regionCount: result.regionCount,
    elapsedMs: result.elapsedMs,
    sourceUrl,
    requestId,
    createdAt: Date.now()
  });
  await cleanupResults();
  await chrome.tabs.create({ url: chrome.runtime.getURL(`result.html?id=${encodeURIComponent(id)}`) });
}

async function requestTranslation(apiBaseUrl, settings, sourceBlob, fileName, sourceUrl) {
  const form = new FormData();
  form.append("image", sourceBlob, fileName);
  form.append("source_url", sourceUrl || "");
  form.append("source_language", settings.sourceLanguage);
  form.append("target_language", settings.targetLanguage);
  const response = await fetch(`${apiBaseUrl}/v1/translate-image`, { method: "POST", body: form });
  if (!response.ok) {
    let detail = `翻译服务返回 HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      // Keep the status when the response body is not JSON.
    }
    throw new Error(detail);
  }
  return {
    translatedBlob: await response.blob(),
    sourceLanguage: response.headers.get("X-Detected-Language") || settings.sourceLanguage,
    regionCount: response.headers.get("X-Region-Count") || "0",
    elapsedMs: response.headers.get("X-Elapsed-Ms") || "0"
  };
}

async function sendToTab(tabId, message) {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (error) {
    if (String(error).includes("Receiving end does not exist")) {
      throw new Error("当前页面不允许插件修改，请在普通网页图片上重试");
    }
    throw error;
  }
}

function isMissingContentScript(error) {
  const message = String(error);
  return message.includes("当前页面不允许插件修改")
    || message.includes("当前页面未找到目标图片")
    || message.includes("Receiving end does not exist");
}

function isHttpUrl(value) {
  try {
    return ["http:", "https:"].includes(new URL(value).protocol);
  } catch (_) {
    return false;
  }
}

function dataUrlToBlob(dataUrl) {
  const [header, encoded] = dataUrl.split(",", 2);
  const mimeType = header.match(/^data:([^;]+)/i)?.[1] || "image/png";
  const binary = atob(encoded);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return new Blob([bytes], { type: mimeType });
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("image-translator", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("results", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function putResult(result) {
  const database = await openDatabase();
  await new Promise((resolve, reject) => {
    const transaction = database.transaction("results", "readwrite");
    transaction.objectStore("results").put(result);
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

async function cleanupResults() {
  const database = await openDatabase();
  await new Promise((resolve, reject) => {
    const transaction = database.transaction("results", "readwrite");
    const store = transaction.objectStore("results");
    const request = store.openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      if (cursor.value.createdAt && Date.now() - cursor.value.createdAt > 60 * 60 * 1000) {
        cursor.delete();
      }
      cursor.continue();
    };
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

async function openErrorResult(message) {
  const id = crypto.randomUUID();
  await putResult({ id, error: message, createdAt: Date.now() });
  await chrome.tabs.create({ url: chrome.runtime.getURL(`result.html?id=${encodeURIComponent(id)}`) });
}

async function blobToDataUrl(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const chunkSize = 32 * 1024;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return `data:${blob.type || "image/png"};base64,${btoa(binary)}`;
}

function fileNameFor(url, mimeType) {
  try {
    const name = new URL(url).pathname.split("/").pop();
    if (name && name.includes(".")) return name;
  } catch (_) {
    // Fall back to a MIME-derived name.
  }
  const extension = mimeType.split("/")[1]?.replace("jpeg", "jpg") || "png";
  return `image.${extension}`;
}
