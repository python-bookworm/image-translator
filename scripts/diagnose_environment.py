from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def module_status() -> None:
    modules = (
        "fastapi",
        "uvicorn",
        "multipart",
        "pydantic_settings",
        "transformers",
        "sentencepiece",
        "fasttext",
        "cv2",
        "PIL",
    )
    print("modules:")
    for module in modules:
        installed = bool(importlib.util.find_spec(module))
        print(f"  {module}: {'installed' if installed else 'missing'}")
        if module != "fasttext" and not installed:
            ERRORS.append(f"missing module: {module}")


def paddle_status() -> None:
    try:
        import paddle

        print("paddle:")
        print(f"  version: {paddle.__version__}")
        print(f"  compiled_with_cuda: {paddle.device.is_compiled_with_cuda()}")
        print(f"  device: {paddle.device.get_device()}")
        print(f"  gpu_count: {paddle.device.cuda.device_count()}")
    except Exception as exc:
        print(f"paddle: ERROR {type(exc).__name__}: {exc}")
        ERRORS.append(f"paddle import failed: {exc}")


def torch_status() -> None:
    try:
        import torch

        print("torch:")
        print(f"  version: {torch.__version__}")
        print(f"  cuda_available: {torch.cuda.is_available()}")
        print(f"  cuda_runtime: {torch.version.cuda}")
        print(f"  gpu_count: {torch.cuda.device_count()}")
    except Exception as exc:
        print(f"torch: ERROR {type(exc).__name__}: {exc}")
        ERRORS.append(f"torch import failed: {exc}")


def model_status() -> None:
    nllb = ROOT / "models" / "nllb-200-distilled-600M"
    expected = (
        "config.json",
        "generation_config.json",
        "pytorch_model.bin",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
    )
    print("nllb:")
    for name in expected:
        path = nllb / name
        print(f"  {name}: {'ok' if path.is_file() else 'missing'}")
        if not path.is_file():
            ERRORS.append(f"missing NLLB file: {name}")
    config_path = nllb / "config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        print(f"  model_type: {config.get('model_type')}")


if __name__ == "__main__":
    print(f"python: {sys.executable}")
    print(f"version: {sys.version.split()[0]}")
    print(f"project: {ROOT}")
    module_status()
    paddle_status()
    torch_status()
    model_status()
    if ERRORS:
        print("readiness: FAILED")
        for error in ERRORS:
            print(f"  - {error}")
        raise SystemExit(1)
    print("readiness: OK")

