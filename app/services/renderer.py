from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.domain import TranslatedRegion


class ImageRenderer:
    def __init__(self, settings: Settings) -> None:
        self._font_path = settings.render_font_path
        self._min_font_size = settings.render_min_font_size
        self._max_font_size = settings.render_max_font_size
        self._inpaint_radius = settings.render_inpaint_radius
        if not Path(self._font_path).is_file():
            raise FileNotFoundError(f"Rendering font not found: {self._font_path}")

    def render(self, image_bgr: np.ndarray, regions: list[TranslatedRegion]) -> np.ndarray:
        if not regions:
            return image_bgr.copy()
        mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
        for region in regions:
            polygon = np.rint(region.source.polygon).astype(np.int32)
            cv2.fillPoly(mask, [polygon], 255)
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
        cleaned = cv2.inpaint(image_bgr, mask, self._inpaint_radius, cv2.INPAINT_TELEA)

        canvas = Image.fromarray(cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(canvas)
        for region in regions:
            self._draw_region(draw, image_bgr, region)
        return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)

    def _draw_region(
        self,
        draw: ImageDraw.ImageDraw,
        original_bgr: np.ndarray,
        region: TranslatedRegion,
    ) -> None:
        points = region.source.polygon
        left, top = np.floor(points.min(axis=0)).astype(int)
        right, bottom = np.ceil(points.max(axis=0)).astype(int)
        width, height = max(1, right - left), max(1, bottom - top)
        color = _contrasting_color(original_bgr, points)
        font, lines = self._fit_text(draw, region.translated_text, width, height)
        line_height = max(1, draw.textbbox((0, 0), "Ag", font=font)[3])
        total_height = line_height * len(lines)
        y = top + max(0, (height - total_height) // 2)
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font)
            line_width = box[2] - box[0]
            x = left + max(0, (width - line_width) // 2)
            draw.text((x, y), line, font=font, fill=color, stroke_width=1, stroke_fill=_stroke(color))
            y += line_height

    def _fit_text(
        self, draw: ImageDraw.ImageDraw, text: str, width: int, height: int
    ) -> tuple[ImageFont.FreeTypeFont, list[str]]:
        upper = min(self._max_font_size, max(self._min_font_size, int(height * 0.9)))
        for size in range(upper, self._min_font_size - 1, -1):
            font = ImageFont.truetype(str(self._font_path), size=size)
            lines = _wrap(draw, text, font, width)
            line_height = max(1, draw.textbbox((0, 0), "Ag", font=font)[3])
            if lines and line_height * len(lines) <= height:
                return font, lines
        font = ImageFont.truetype(str(self._font_path), size=self._min_font_size)
        return font, _wrap(draw, text, font, width)


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text.strip():
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _contrasting_color(image_bgr: np.ndarray, polygon: np.ndarray) -> tuple[int, int, int]:
    mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(polygon).astype(np.int32)], 255)
    mean_bgr = cv2.mean(image_bgr, mask=mask)[:3]
    luminance = 0.114 * mean_bgr[0] + 0.587 * mean_bgr[1] + 0.299 * mean_bgr[2]
    return (20, 20, 20) if luminance > 145 else (245, 245, 245)


def _stroke(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return (255, 255, 255) if color[0] < 128 else (0, 0, 0)

