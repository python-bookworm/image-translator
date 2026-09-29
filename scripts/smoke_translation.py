from __future__ import annotations

import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.translator import NllbTranslator  # noqa: E402


if __name__ == "__main__":
    settings = get_settings()
    print(
        f"device={settings.translation_device} "
        f"dtype={settings.translation_dtype} model={settings.translation_model_dir}"
    )
    started = time.perf_counter()
    translator = NllbTranslator(settings)
    loaded_at = time.perf_counter()
    detected, translated = translator.translate(
        ["Image translation test", "Production line status is normal"],
        source_language="en",
        target_language="zh",
    )
    finished_at = time.perf_counter()
    print(f"source_language={detected}")
    for source, target in zip(
        ["Image translation test", "Production line status is normal"], translated, strict=True
    ):
        print(f"{source} -> {target}")
    print(f"load_seconds={loaded_at - started:.3f}")
    print(f"translate_seconds={finished_at - loaded_at:.3f}")

