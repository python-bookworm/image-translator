from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


NLLB_FILES = {
    "config.json": None,
    "generation_config.json": None,
    "pytorch_model.bin": "c266c2cfd19758b6d09c1fc31ecdf1e485509035f6b51dfe84f1ada83eefcc42",
    "sentencepiece.bpe.model": None,
    "special_tokens_map.json": None,
    "tokenizer.json": "e316b82de11d0f951f370943b3c438311629547285129b0b81dadabd01bca665",
    "tokenizer_config.json": None,
}
PADDLE_MODELS = (
    "PP-OCRv5_server_det",
    "PP-OCRv5_server_rec",
    "PP-LCNet_x1_0_textline_ori",
)
PADDLE_FILES = ("config.json", "inference.json", "inference.pdiparams", "inference.yml")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(root: Path, verify_hashes: bool) -> list[str]:
    errors: list[str] = []
    nllb = root / "nllb-200-distilled-600M"
    for name, expected_hash in NLLB_FILES.items():
        path = nllb / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing NLLB file: {path}")
        elif verify_hashes and expected_hash and sha256(path) != expected_hash:
            errors.append(f"NLLB checksum mismatch: {path}")

    config_path = nllb / "config.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if config.get("model_type") != "m2m_100":
                errors.append(f"unexpected NLLB model_type: {config.get('model_type')}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid NLLB config: {exc}")

    for model in PADDLE_MODELS:
        directory = root / "v5" / model
        for name in PADDLE_FILES:
            path = directory / name
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"missing Paddle file: {path}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate local OCR and NLLB model files")
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--verify-hashes", action="store_true")
    args = parser.parse_args()
    failures = validate(args.models, args.verify_hashes)
    if failures:
        print("Model validation FAILED")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print(f"Model validation OK: {args.models.resolve()}")

