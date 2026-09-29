let record;
let translatedUrl;
let originalUrl;

const image = document.querySelector("#resultImage");
const status = document.querySelector("#status");
const metadata = document.querySelector("#metadata");
const translatedButton = document.querySelector("#showTranslated");
const originalButton = document.querySelector("#showOriginal");
const downloadButton = document.querySelector("#download");

initialize().catch((error) => showError(error.message || String(error)));

async function initialize() {
  const id = new URLSearchParams(location.search).get("id");
  if (!id) throw new Error("Missing result id");
  record = await getResult(id);
  if (!record) throw new Error("Translation result was not found or has expired");
  if (record.error) throw new Error(record.error);

  translatedUrl = URL.createObjectURL(record.translatedBlob);
  originalUrl = URL.createObjectURL(record.sourceBlob);
  metadata.textContent = `${record.sourceLanguage} to ${record.targetLanguage} | ${record.regionCount} regions | ${record.elapsedMs} ms`;
  showImage(translatedUrl, true);
}

translatedButton.addEventListener("click", () => showImage(translatedUrl, true));
originalButton.addEventListener("click", () => showImage(originalUrl, false));
downloadButton.addEventListener("click", () => {
  if (!translatedUrl) return;
  const anchor = document.createElement("a");
  anchor.href = translatedUrl;
  anchor.download = `translated-${Date.now()}.png`;
  anchor.click();
});

function showImage(url, translated) {
  image.src = url;
  image.hidden = false;
  status.hidden = true;
  translatedButton.classList.toggle("active", translated);
  originalButton.classList.toggle("active", !translated);
}

function showError(message) {
  status.textContent = message;
  status.style.color = "#ff9c8f";
  downloadButton.disabled = true;
  translatedButton.disabled = true;
  originalButton.disabled = true;
}

function getResult(id) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("image-translator", 1);
    request.onsuccess = () => {
      const database = request.result;
      const transaction = database.transaction("results", "readonly");
      const getRequest = transaction.objectStore("results").get(id);
      getRequest.onsuccess = () => resolve(getRequest.result);
      getRequest.onerror = () => reject(getRequest.error);
      transaction.oncomplete = () => database.close();
    };
    request.onerror = () => reject(request.error);
  });
}

window.addEventListener("unload", () => {
  if (translatedUrl) URL.revokeObjectURL(translatedUrl);
  if (originalUrl) URL.revokeObjectURL(originalUrl);
});

