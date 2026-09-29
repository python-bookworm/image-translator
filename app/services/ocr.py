import logging
from collections.abc import Iterable
from typing import Any

import numpy as np

from app.config import Settings
from app.domain import TextRegion

logger = logging.getLogger(__name__)


class PaddleOcrService:
    def __init__(self, settings: Settings) -> None:
        from paddleocr import PaddleOCR

        self._min_score = settings.ocr_min_score
        self._engine = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            text_detection_model_dir=str(settings.ocr_det_model_dir),
            text_recognition_model_dir=str(settings.ocr_rec_model_dir),
            use_textline_orientation=True,
            textline_orientation_model_dir=str(settings.ocr_orientation_model_dir),
            device=settings.ocr_device,
            enable_mkldnn=False,
            cpu_threads=settings.ocr_cpu_threads,
            precision=settings.ocr_precision,
            text_det_unclip_ratio=2.0,
        )
        if settings.ocr_warmup:
            logger.info("Warming up PaddleOCR")
            image = np.zeros((640, 640, 3), dtype=np.uint8)
            self._engine.predict(image)

    def recognize(self, image_bgr: np.ndarray) -> list[TextRegion]:
        logger.info("Starting PaddleOCR recognition: image_shape=%s", image_bgr.shape)
        results = self._engine.predict(image_bgr)
        regions: list[TextRegion] = []
        next_id = 0
        for result in results or []:
            payload = _result_payload(result)
            texts = _as_list(payload.get("rec_texts"))
            scores = _as_list(payload.get("rec_scores"))
            polygon_value = payload.get("rec_polys")
            if polygon_value is None:
                polygon_value = payload.get("dt_polys")
            polygons = list(polygon_value) if polygon_value is not None else []
            for polygon, text, score in _zip_longest_shortest(polygons, texts, scores):
                clean_text = str(text).strip()
                confidence = float(score)
                points = np.asarray(polygon, dtype=np.float32)
                if clean_text and confidence >= self._min_score and points.shape == (4, 2):
                    regions.append(
                        TextRegion(
                            id=f"region-{next_id:04d}",
                            polygon=points,
                            text=clean_text,
                            score=confidence,
                        )
                    )
                    next_id += 1
        ordered = sorted(regions, key=_reading_order)
        logger.info("PaddleOCR recognition finished: accepted_regions=%d", len(ordered))
        return ordered


def _result_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    inner = getattr(result, "res", None)
    if isinstance(inner, dict):
        return inner
    try:
        return dict(result)
    except (TypeError, ValueError):
        logger.warning("Unsupported PaddleOCR result type: %s", type(result).__name__)
        return {}


def _zip_longest_shortest(*values: Iterable[Any]) -> zip:
    return zip(*values)


def _as_list(value: Any) -> list[Any]:
    return list(value) if value is not None else []


def _reading_order(region: TextRegion) -> tuple[float, float]:
    return float(region.polygon[:, 1].min()), float(region.polygon[:, 0].min())
