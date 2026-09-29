import logging
import time
from dataclasses import dataclass
from threading import Lock

import cv2
import numpy as np

from app.config import Settings
from app.domain import TranslatedRegion
from app.services.ocr import PaddleOcrService
from app.services.renderer import ImageRenderer
from app.services.translator import create_translator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    image_png: bytes
    source_language: str
    region_count: int
    elapsed_ms: int


class ImageTranslationPipeline:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ocr = PaddleOcrService(settings)
        self._translator = create_translator(settings)
        self._renderer = ImageRenderer(settings)
        self._inference_lock = Lock()

    def process(
        self,
        content: bytes,
        source_language: str,
        target_language: str,
        request_id: str = "-",
    ) -> PipelineResult:
        started = time.perf_counter()
        image = self._decode(content)
        logger.info(
            "[%s] Image decoded successfully: width=%d height=%d channels=%d",
            request_id,
            image.shape[1],
            image.shape[0],
            image.shape[2] if image.ndim == 3 else 1,
        )
        # Paddle and the tokenizer mutate inference state; serialize the small internal workload.
        with self._inference_lock:
            regions = self._ocr.recognize(image)
            logger.info("[%s] OCR completed: region_count=%d", request_id, len(regions))
            for region in regions:
                logger.info(
                    "[%s] OCR region: id=%s score=%.4f text=%s",
                    request_id,
                    region.id,
                    region.score,
                    _log_text(region.text),
                )
            detected, translations = self._translator.translate(
                [region.text for region in regions], source_language, target_language
            )
            logger.info(
                "[%s] Translation completed: detected_language=%s result_count=%d",
                request_id,
                detected,
                len(translations),
            )
            for region, translated in zip(regions, translations, strict=True):
                logger.info(
                    "[%s] Translation result: id=%s source=%s target=%s",
                    request_id,
                    region.id,
                    _log_text(region.text),
                    _log_text(translated),
                )
        translated_regions = [
            TranslatedRegion(source=region, translated_text=translated)
            for region, translated in zip(regions, translations, strict=True)
        ]
        rendered = self._renderer.render(image, translated_regions)
        success, encoded = cv2.imencode(".png", rendered)
        if not success:
            raise RuntimeError("Failed to encode translated image")
        logger.info("[%s] Image rendered and encoded: png_bytes=%d", request_id, encoded.size)
        return PipelineResult(
            image_png=encoded.tobytes(),
            source_language=detected,
            region_count=len(regions),
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )

    def _decode(self, content: bytes) -> np.ndarray:
        if not content:
            raise ValueError("The uploaded image is empty")
        if len(content) > self._settings.max_image_bytes:
            raise ValueError("The uploaded image exceeds MAX_IMAGE_BYTES")
        image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unsupported or invalid image")
        if image.shape[0] * image.shape[1] > self._settings.max_image_pixels:
            raise ValueError("The decoded image exceeds MAX_IMAGE_PIXELS")
        return image


def _log_text(value: str, limit: int = 1000) -> str:
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    return text if len(text) <= limit else f"{text[:limit]}...<truncated>"
