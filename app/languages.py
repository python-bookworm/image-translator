from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    name_zh: str
    nllb_code: str


# POC list exposed by the extension. NLLB supports more languages and this table can grow
# without changing the translation service.
LANGUAGES = (
    Language("auto", "Auto detect", "自动识别", ""),
    Language("zh", "Chinese (Simplified)", "中文（简体）", "zho_Hans"),
    Language("en", "English", "英语", "eng_Latn"),
    Language("ja", "Japanese", "日语", "jpn_Jpan"),
    Language("ko", "Korean", "韩语", "kor_Hang"),
    Language("fr", "French", "法语", "fra_Latn"),
    Language("de", "German", "德语", "deu_Latn"),
    Language("es", "Spanish", "西班牙语", "spa_Latn"),
    Language("pt", "Portuguese", "葡萄牙语", "por_Latn"),
    Language("ru", "Russian", "俄语", "rus_Cyrl"),
    Language("ar", "Arabic", "阿拉伯语", "arb_Arab"),
    Language("th", "Thai", "泰语", "tha_Thai"),
    Language("vi", "Vietnamese", "越南语", "vie_Latn"),
    Language("id", "Indonesian", "印度尼西亚语", "ind_Latn"),
    Language("ms", "Malay", "马来语", "zsm_Latn"),
    Language("hi", "Hindi", "印地语", "hin_Deva"),
    Language("bn", "Bengali", "孟加拉语", "ben_Beng"),
    Language("ur", "Urdu", "乌尔都语", "urd_Arab"),
    Language("tr", "Turkish", "土耳其语", "tur_Latn"),
    Language("pl", "Polish", "波兰语", "pol_Latn"),
    Language("uk", "Ukrainian", "乌克兰语", "ukr_Cyrl"),
    Language("nl", "Dutch", "荷兰语", "nld_Latn"),
    Language("it", "Italian", "意大利语", "ita_Latn"),
    Language("km", "Khmer", "高棉语", "khm_Khmr"),
    Language("lo", "Lao", "老挝语", "lao_Laoo"),
    Language("my", "Burmese", "缅甸语", "mya_Mymr"),
    Language("sw", "Swahili", "斯瓦希里语", "swh_Latn"),
    Language("am", "Amharic", "阿姆哈拉语", "amh_Ethi"),
    Language("he", "Hebrew", "希伯来语", "heb_Hebr"),
)

BY_CODE = {language.code: language for language in LANGUAGES}

# fastText emits ISO-like labels. Add aliases where its code differs from ours.
FASTTEXT_ALIASES = {"zh": "zh", "jp": "ja", "iw": "he"}


def to_nllb(code: str) -> str:
    try:
        return BY_CODE[code].nllb_code
    except KeyError as exc:
        raise ValueError(f"Unsupported language code: {code}") from exc
