from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    compose_path = ROOT / "compose.yaml"
    dockerfile_path = ROOT / "Dockerfile"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service = compose["services"]["image-translator"]
    errors: list[str] = []

    if service.get("gpus") != "all":
        errors.append("compose service must request all exposed GPUs")
    if service.get("volumes") != ["./models:/opt/image-translator/models:ro"]:
        errors.append("models must be mounted read-only at the expected container path")
    if service.get("environment", {}).get("TRANSLATION_DEVICE") != "${TRANSLATION_DEVICE:-cuda:0}":
        errors.append("translation device must default to cuda:0")
    if service.get("environment", {}).get("OCR_DEVICE") != "${OCR_DEVICE:-gpu:0}":
        errors.append("OCR device must default to gpu:0")

    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    required_fragments = (
        "nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04",
        "paddlepaddle-gpu==${PADDLE_VERSION}",
        "torch==${TORCH_VERSION}",
        "HEALTHCHECK",
        'CMD ["scripts/docker_entrypoint.sh"]',
    )
    for fragment in required_fragments:
        if fragment not in dockerfile:
            errors.append(f"Dockerfile is missing: {fragment}")
    if re.search(r"COPY\s+models", dockerfile):
        errors.append("Dockerfile must not copy model files into the image")

    if errors:
        print("Deployment configuration FAILED")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("Deployment configuration OK")


if __name__ == "__main__":
    main()

