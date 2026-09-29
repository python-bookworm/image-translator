from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import paddle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print(subprocess.run(["nvidia-smi"], check=True, capture_output=True, text=True).stdout)
    print(f"paddle={paddle.__version__} paddle_cuda={paddle.device.is_compiled_with_cuda()}")
    print(f"paddle_gpu_count={paddle.device.cuda.device_count()}")
    if not paddle.device.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1:
        raise SystemExit("PaddlePaddle cannot access an NVIDIA GPU")
    print(f"translation_provider={settings.translation_provider}")

    requires_torch = (
        settings.translation_provider == "nllb"
        or settings.llm_fallback_to_nllb
    )
    if requires_torch:
        try:
            import torch
        except ImportError as exc:
            raise SystemExit(
                "PyTorch is required by NLLB or LLM_FALLBACK_TO_NLLB; install it or disable fallback"
            ) from exc
        print(f"torch={torch.__version__} torch_cuda={torch.version.cuda}")
        print(
            f"torch_cuda_available={torch.cuda.is_available()} "
            f"torch_gpu_count={torch.cuda.device_count()}"
        )
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise SystemExit("PyTorch cannot access an NVIDIA GPU")
        print(f"gpu={torch.cuda.get_device_name(0)}")
    else:
        print("torch_check=skipped (LLM translation without NLLB fallback)")


if __name__ == "__main__":
    main()
