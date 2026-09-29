from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.ocr import PaddleOcrService  # noqa: E402


def make_test_image(font_path: Path) -> np.ndarray:
    image = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), size=58)
    draw.text((40, 35), "Image translation test 2026", font=font, fill="black")
    draw.text((40, 115), "图片翻译识别测试", font=font, fill="black")
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


if __name__ == "__main__":
    settings = get_settings()
    print(f"device={settings.ocr_device} precision={settings.ocr_precision}")
    print(f"detector={settings.ocr_det_model_dir}")
    print(f"recognizer={settings.ocr_rec_model_dir}")
    image = make_test_image(settings.render_font_path)
    service = PaddleOcrService(settings)
    regions = service.recognize(image)
    print(f"regions={len(regions)}")
    for region in regions:
        print(f"{region.id}\t{region.score:.4f}\t{region.text}")
    if not regions:
        raise SystemExit("OCR returned no regions")

