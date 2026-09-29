import json
import logging
import time
from collections.abc import Sequence
from typing import Protocol

import requests

from app.config import Settings
from app.languages import BY_CODE, FASTTEXT_ALIASES, to_nllb

logger = logging.getLogger(__name__)


class Translator(Protocol):
    def translate(
        self,
        texts: Sequence[str],
        source_language: str,
        target_language: str,
    ) -> tuple[str, list[str]]: ...


def create_translator(settings: Settings) -> Translator:
    if settings.translation_provider == "llm":
        fallback = LazyNllbTranslator(settings) if settings.llm_fallback_to_nllb else None
        return LlmTranslator(settings, fallback=fallback)
    return NllbTranslator(settings)


class LazyNllbTranslator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._translator: NllbTranslator | None = None

    def translate(
        self,
        texts: Sequence[str],
        source_language: str,
        target_language: str,
    ) -> tuple[str, list[str]]:
        if self._translator is None:
            self._translator = NllbTranslator(self._settings)
        return self._translator.translate(texts, source_language, target_language)


class LlmTranslator:
    def __init__(self, settings: Settings, fallback: Translator | None = None) -> None:
        self._settings = settings
        self._fallback = fallback
        self._url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        self._api_key = settings.llm_api_key.get_secret_value()
        self._session = requests.Session()
        self._session.trust_env = settings.llm_use_env_proxy
        if settings.llm_proxy:
            self._session.proxies.update({"http": settings.llm_proxy, "https": settings.llm_proxy})

    def translate(
        self,
        texts: Sequence[str],
        source_language: str,
        target_language: str,
    ) -> tuple[str, list[str]]:
        if not texts:
            return source_language, []
        if source_language == "auto":
            try:
                detected, translated = self._translate_auto(texts, target_language)
                return detected, translated
            except Exception as exc:
                return self._fallback_or_raise(texts, source_language, target_language, exc)
        if source_language == target_language:
            return source_language, list(texts)

        translated: list[str] = []
        try:
            for batch in self._build_batches(texts):
                _, batch_translated = self._translate_batch_with_recovery(
                    batch, source_language, target_language
                )
                translated.extend(batch_translated)
        except Exception as exc:
            return self._fallback_or_raise(texts, source_language, target_language, exc)
        return source_language, translated

    def _translate_auto(
        self, texts: Sequence[str], target_language: str
    ) -> tuple[str, list[str]]:
        translated: list[str] = []
        detected_languages: list[str] = []
        for batch in self._build_batches(texts):
            detected, batch_translated = self._translate_batch_with_recovery(
                batch, "auto", target_language
            )
            detected_languages.append(detected)
            translated.extend(batch_translated)
        if not detected_languages:
            raise ValueError("LLM did not detect a source language")
        if len(set(detected_languages)) > 1:
            logger.warning("OCR batches contain multiple source languages: %s", detected_languages)
        return detected_languages[0], translated

    def _build_batches(self, texts: Sequence[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        current: list[str] = []
        current_chars = 0
        max_chars = self._settings.llm_max_batch_chars
        for text in texts:
            text_chars = len(text)
            if current and (
                len(current) >= self._settings.llm_batch_size
                or current_chars + text_chars > max_chars
            ):
                batches.append(current)
                current = []
                current_chars = 0
            current.append(text)
            current_chars += text_chars
        if current:
            batches.append(current)
        return batches

    def _translate_batch_with_recovery(
        self, texts: list[str], source_language: str, target_language: str
    ) -> tuple[str, list[str]]:
        """Recover incomplete model output without weakening ID validation."""
        if not texts:
            return source_language, []
        try:
            return self._translate_batch(texts, source_language, target_language)
        except _IncompleteTranslation as first_error:
            expected = list(range(len(texts)))
            translations = dict(first_error.translations)
            detected = first_error.detected_language
            missing = [index for index in expected if index not in translations]
            logger.warning(
                "LLM partial response: requested=%d returned=%d missing=%s finish_reason=%s",
                len(texts),
                len(translations),
                missing,
                first_error.finish_reason,
            )

            for attempt in range(self._settings.llm_retry_count):
                if not missing:
                    break
                if self._settings.llm_retry_backoff_seconds:
                    time.sleep(self._settings.llm_retry_backoff_seconds * (attempt + 1))
                retry_texts = [texts[index] for index in missing]
                try:
                    retry_detected, retry_translated = self._translate_batch(
                        retry_texts, source_language, target_language
                    )
                    for index, value in zip(missing, retry_translated):
                        translations[index] = value
                    detected = detected or retry_detected
                    missing = [index for index in expected if index not in translations]
                except _IncompleteTranslation as retry_error:
                    # A retry uses local IDs, so retain only the complete prefix/response
                    # that can be mapped to this retry request; unresolved items are split below.
                    logger.warning(
                        "LLM retry incomplete: attempt=%d requested=%d returned=%d missing=%s",
                        attempt + 1,
                        len(retry_texts),
                        len(retry_error.translations),
                        retry_error.missing,
                    )
                    for local_id, value in retry_error.translations.items():
                        if local_id < len(missing):
                            translations[missing[local_id]] = value
                    detected = detected or retry_error.detected_language
                    missing = [index for index in expected if index not in translations]
            if not missing:
                return detected or source_language, [translations[index] for index in expected]

            # The first response was likely output-truncated. Smaller recursive calls
            # make the recovery independent of the gateway's generation limit.
            if len(texts) == 1:
                raise first_error
            recovered: dict[int, str] = {}
            for index in missing:
                try:
                    child_detected, child_values = self._translate_batch_with_recovery(
                        [texts[index]], source_language, target_language
                    )
                except Exception:
                    raise first_error
                recovered[index] = child_values[0]
                detected = detected or child_detected
            translations.update(recovered)
            return detected or source_language, [translations[index] for index in expected]

    def _translate_batch_once(
        self, texts: list[str], source_language: str, target_language: str
    ) -> tuple[str, list[str]]:
        return self._translate_batch(texts, source_language, target_language)

    def _translate_batch(
        self, texts: list[str], source_language: str, target_language: str
    ) -> tuple[str, list[str]]:
        logger.info(
            "LLM translation request: url=%s model=%s source_language=%s "
            "target_language=%s item_count=%d texts=%s",
            self._url,
            self._settings.llm_model,
            source_language,
            target_language,
            len(texts),
            _log_texts(texts),
        )
        source_name = "the detected source language" if source_language == "auto" else _language_name(source_language)
        target_name = _language_name(target_language)
        items = [{"id": index, "text": text} for index, text in enumerate(texts)]
        system_message = (
            "You are a professional image-text translator. Translate faithfully and concisely. "
            "Preserve names, numbers, units, punctuation, placeholders and line intent. "
            "Do not explain or add content. Return JSON only in this exact shape: "
            '{"source_language":"tr","translations":[{"id":0,"text":"translated text"}]}. '
            "Return exactly one item for every input id and keep each id unchanged. "
            "Never stop before all required ids are returned."
        )
        user_message = (
            f"Translate the following OCR text from {source_name} "
            f"to {target_name} ({target_language}).\n"
            "If the source language is unknown, identify it from the OCR text. "
            "Use a lowercase ISO-639-1 code in source_language. It must be one of: "
            f"{', '.join(code for code in BY_CODE if code != 'auto')}.\n"
            f"Required translation ids, exactly once each: {list(range(len(texts)))}\n"
            f"Input JSON:\n{json.dumps({'items': items}, ensure_ascii=False)}"
        )
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = self._session.post(
                self._url,
                headers=headers,
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": self._settings.llm_temperature,
                    "stream": False,
                    "max_tokens": self._settings.llm_max_output_tokens,
                },
                timeout=self._settings.llm_timeout_seconds,
            )
        except requests.RequestException:
            logger.exception(
                "LLM request failed: url=%s model=%s proxy_mode=%s explicit_proxy=%s",
                self._url,
                self._settings.llm_model,
                self._settings.llm_use_env_proxy,
                bool(self._settings.llm_proxy),
            )
            raise
        logger.info(
            "LLM HTTP response: status=%d response_bytes=%d",
            response.status_code,
            len(response.content),
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()[:1000]
            logger.error(
                "LLM HTTP error: status=%d detail=%s",
                response.status_code,
                _log_text(detail),
            )
            raise RuntimeError(
                f"LLM service returned HTTP {response.status_code}: {detail or '<empty body>'}"
            ) from exc
        try:
            response_payload = response.json()
            choice = response_payload["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("LLM response does not contain choices[0].message.content") from exc
        finish_reason = choice.get("finish_reason")
        logger.info(
            "LLM response received: status=%d response_chars=%d finish_reason=%s content=%s",
            response.status_code,
            len(content),
            finish_reason,
            _log_text(content),
        )
        detected = (
            parse_source_language_response(content)
            if source_language == "auto"
            else source_language
        )
        try:
            translated = parse_translation_response(content, len(texts))
        except ValueError as exc:
            partial = _parse_partial_translations(content)
            missing = sorted(set(range(len(texts))) - set(partial))
            if partial and missing:
                raise _IncompleteTranslation(
                    str(exc), partial, detected, missing, finish_reason
                ) from exc
            raise
        logger.info(
            "LLM response parsed: detected_language=%s translations=%s",
            detected,
            _log_texts(translated),
        )
        return detected, translated

    def _fallback_or_raise(
        self,
        texts: Sequence[str],
        source_language: str,
        target_language: str,
        error: Exception,
    ) -> tuple[str, list[str]]:
        if self._fallback is None:
            raise error
        if source_language == "auto" and self._settings.language_id_model is None:
            logger.warning(
                "LLM translation failed and NLLB auto-language fallback is unavailable: %s",
                error,
            )
            raise error
        logger.warning("LLM translation failed; falling back to NLLB: %s", error)
        return self._fallback.translate(texts, source_language, target_language)


class _IncompleteTranslation(ValueError):
    def __init__(
        self,
        message: str,
        translations: dict[int, str],
        detected_language: str,
        missing: list[int],
        finish_reason: str | None,
    ) -> None:
        super().__init__(message)
        self.translations = translations
        self.detected_language = detected_language
        self.missing = missing
        self.finish_reason = finish_reason


class NllbTranslator:
    def __init__(self, settings: Settings) -> None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self._torch = torch
        self._settings = settings
        self._device = torch.device(settings.translation_device)
        dtype = getattr(torch, settings.translation_dtype)
        model_path = str(settings.translation_model_dir)
        self._tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            model_path,
            local_files_only=True,
            torch_dtype=dtype,
        ).to(self._device)
        self._model.eval()
        self._detector = self._load_detector(settings)

    def translate(
        self,
        texts: Sequence[str],
        source_language: str,
        target_language: str,
    ) -> tuple[str, list[str]]:
        if not texts:
            return source_language, []
        detected = self.detect_language(texts) if source_language == "auto" else source_language
        if detected == target_language:
            return detected, list(texts)

        source_nllb = to_nllb(detected)
        target_nllb = to_nllb(target_language)
        self._tokenizer.src_lang = source_nllb
        translated: list[str] = []
        batch_size = self._settings.translation_batch_size
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            encoded = self._tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self._settings.translation_max_input_tokens,
            ).to(self._device)
            with self._torch.inference_mode():
                output = self._model.generate(
                    **encoded,
                    forced_bos_token_id=self._tokenizer.convert_tokens_to_ids(target_nllb),
                    max_new_tokens=self._settings.translation_max_new_tokens,
                    num_beams=1,
                )
            translated.extend(self._tokenizer.batch_decode(output, skip_special_tokens=True))
        return detected, translated

    def detect_language(self, texts: Sequence[str]) -> str:
        if self._detector is None:
            raise ValueError(
                "source_language=auto requires LANGUAGE_ID_MODEL; select a source language "
                "or configure lid.176.bin"
            )
        sample = " ".join(texts).replace("\n", " ")[:4000]
        labels, probabilities = self._detector.predict(sample, k=1)
        raw_code = labels[0].removeprefix("__label__")
        code = FASTTEXT_ALIASES.get(raw_code, raw_code)
        logger.info("Detected source language %s (%.3f)", code, probabilities[0])
        to_nllb(code)
        return code

    @staticmethod
    def _load_detector(settings: Settings):
        if not settings.language_id_model:
            return None
        import fasttext

        return fasttext.load_model(str(settings.language_id_model))


def parse_translation_response(content: str, expected_count: int) -> list[str]:
    payload = _extract_json_object(content)
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise ValueError("LLM JSON must contain a translations array")

    by_id: dict[int, str] = {}
    for item in translations:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            raise ValueError("Each LLM translation must contain an integer id")
        item_id = item["id"]
        text = item.get("text")
        if item_id in by_id:
            raise ValueError(f"LLM returned duplicate translation id {item_id}")
        if not isinstance(text, str):
            raise ValueError(f"LLM translation id {item_id} has no text")
        by_id[item_id] = text.strip()

    expected_ids = set(range(expected_count))
    if set(by_id) != expected_ids:
        missing = sorted(expected_ids - set(by_id))
        unexpected = sorted(set(by_id) - expected_ids)
        raise ValueError(f"LLM translation ids mismatch; missing={missing}, unexpected={unexpected}")
    return [by_id[index] for index in range(expected_count)]


def _parse_partial_translations(content: str) -> dict[int, str]:
    """Best-effort extraction used only to recover an incomplete response."""
    try:
        payload = _extract_json_object(content)
    except ValueError:
        return {}
    translations = payload.get("translations")
    if not isinstance(translations, list):
        return {}
    result: dict[int, str] = {}
    for item in translations:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        text = item.get("text")
        if isinstance(item_id, int) and isinstance(text, str) and item_id not in result:
            result[item_id] = text.strip()
    return result


def parse_source_language_response(content: str) -> str:
    payload = _extract_json_object(content)
    source_language = payload.get("source_language")
    if not isinstance(source_language, str) or source_language not in BY_CODE or source_language == "auto":
        raise ValueError(f"LLM returned unsupported source language: {source_language!r}")
    return source_language


def _extract_json_object(content: str) -> dict:
    start = content.find("{")
    if start < 0:
        raise ValueError("LLM response does not contain JSON")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        character = content[index]
        if escaped:
            escaped = False
            continue
        if character == "\\" and in_string:
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(content[start : index + 1])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON returned by LLM: {exc}") from exc
                if not isinstance(parsed, dict):
                    raise ValueError("LLM JSON response must be an object")
                return parsed
    raise ValueError("LLM response contains incomplete JSON")


def _language_name(code: str) -> str:
    try:
        return BY_CODE[code].name
    except KeyError as exc:
        raise ValueError(f"Unsupported language code: {code}") from exc


def _log_text(value: str, limit: int = 4000) -> str:
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    return text if len(text) <= limit else f"{text[:limit]}...<truncated>"


def _log_texts(values: Sequence[str], limit: int = 4000) -> str:
    return _log_text(json.dumps(list(values), ensure_ascii=False), limit)
