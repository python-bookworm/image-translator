const LANGUAGES = [
  ["auto", "自动识别 / Auto detect"], ["zh", "中文（简体） / Chinese (Simplified)"],
  ["en", "英语 / English"], ["ja", "日语 / Japanese"], ["ko", "韩语 / Korean"],
  ["fr", "法语 / French"], ["de", "德语 / German"], ["es", "西班牙语 / Spanish"],
  ["pt", "葡萄牙语 / Portuguese"], ["ru", "俄语 / Russian"], ["ar", "阿拉伯语 / Arabic"],
  ["th", "泰语 / Thai"], ["vi", "越南语 / Vietnamese"], ["id", "印度尼西亚语 / Indonesian"],
  ["ms", "马来语 / Malay"], ["hi", "印地语 / Hindi"], ["bn", "孟加拉语 / Bengali"],
  ["ur", "乌尔都语 / Urdu"], ["tr", "土耳其语 / Turkish"], ["pl", "波兰语 / Polish"],
  ["uk", "乌克兰语 / Ukrainian"], ["nl", "荷兰语 / Dutch"], ["it", "意大利语 / Italian"],
  ["km", "高棉语 / Khmer"], ["lo", "老挝语 / Lao"], ["my", "缅甸语 / Burmese"],
  ["sw", "斯瓦希里语 / Swahili"], ["am", "阿姆哈拉语 / Amharic"],
  ["he", "希伯来语 / Hebrew"]
];
const DEFAULTS = {
  apiBaseUrl: "http://127.0.0.1:8080",
  sourceLanguage: "en",
  targetLanguage: "zh"
};

const form = document.querySelector("#settingsForm");
const apiBaseUrl = document.querySelector("#apiBaseUrl");
const sourceLanguage = document.querySelector("#sourceLanguage");
const targetLanguage = document.querySelector("#targetLanguage");
const message = document.querySelector("#message");
const testConnection = document.querySelector("#testConnection");

for (const [code, name] of LANGUAGES) {
  sourceLanguage.add(new Option(name, code));
  if (code !== "auto") targetLanguage.add(new Option(name, code));
}

chrome.storage.sync.get(DEFAULTS).then((settings) => {
  apiBaseUrl.value = settings.apiBaseUrl;
  sourceLanguage.value = settings.sourceLanguage;
  targetLanguage.value = settings.targetLanguage;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await chrome.storage.sync.set({
    apiBaseUrl: apiBaseUrl.value.replace(/\/+$/, ""),
    sourceLanguage: sourceLanguage.value,
    targetLanguage: targetLanguage.value
  });
  showMessage("已保存", false);
});

testConnection.addEventListener("click", async () => {
  testConnection.disabled = true;
  showMessage("连接中...", false, 0);
  try {
    const baseUrl = apiBaseUrl.value.replace(/\/+$/, "");
    const response = await fetch(`${baseUrl}/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const health = await response.json();
    const autoText = health.auto_language_detection ? "支持自动识别" : "需手动选择源语言";
    const provider = health.translation_provider === "llm" ? "大模型翻译" : "NLLB 翻译";
    showMessage(`服务正常，${provider}，${autoText}`, false, 4000);
  } catch (error) {
    showMessage(`连接失败：${error.message || error}`, true, 4000);
  } finally {
    testConnection.disabled = false;
  }
});

function showMessage(text, isError, timeout = 1500) {
  message.textContent = text;
  message.style.color = isError ? "#b42318" : "#167a5b";
  if (!timeout) return;
  setTimeout(() => { message.textContent = ""; }, timeout);
}
