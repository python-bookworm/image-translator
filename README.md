# Local Image Translator POC

PaddleOCR 负责识别图片文字和定位，大模型或本地 NLLB 负责翻译，浏览器扩展将翻译后的图片直接替换到当前网页。大模型接口采用 OpenAI 兼容的 `/v1/chat/completions` 协议，详细配置和 Linux 部署步骤见 `LINUX_GPU_DEPLOYMENT.md`。

This proof of concept translates a browser image through an entirely local service:

```text
Chrome/Edge context menu
  -> download selected image
  -> PaddleOCR v5 (local GPU models)
  -> NLLB-200 distilled 600M (local GPU model)
  -> OpenCV inpainting + Pillow text layout
  -> original/translated result page
```

The implementation is intentionally synchronous and single-process. That keeps the first
quality and latency evaluation simple. Add a queue or multiple workers only after measuring
real usage; each worker loads a separate copy of both models into GPU memory. A process-local
lock serializes GPU inference requests in this POC to protect shared model/tokenizer state and
keep peak GPU memory predictable.

## What is included

- FastAPI backend with one `multipart/form-data` image endpoint.
- PaddleOCR v5 adapter based on the supplied local-model initialization pattern.
- NLLB translation to Chinese or English, plus a starter set of source languages.
- Optional fastText `lid.176.bin` automatic language detection.
- Basic OpenCV inpainting and adaptive text rendering.
- Manifest V3 Chrome/Edge extension with a context-menu action, result comparison, and download.
- Linux GPU Docker configuration and model-free unit tests.

## Important POC boundaries

The configured `PP-OCRv5_server_rec` model must recognize the scripts in the source images.
Translation model coverage does not compensate for an OCR recognition model that cannot read
Khmer, Arabic, Devanagari, and other scripts. Test the actual local recognition model against
the target language set first. If it does not cover a script, route by source language to the
corresponding PaddleOCR multilingual recognition model or run separate OCR model instances.

Rendering is deliberately basic. It inpaints the detected polygon and places fitted text inside
its axis-aligned bounding box. Rotated text, vertical layout, complex backgrounds, typography
matching, and paragraph-level regrouping are future quality work. The current build is suited to
measuring the end-to-end flow on screenshots, documents, and relatively plain images.

`blob:` image URLs and protected images that reject extension fetches are not handled yet. Normal
HTTP(S), data URL, and directly opened images are the intended POC inputs. When a directly opened
image has a URL such as `http://host/path/0.jpg`, the extension downloads that URL and opens the
translated result page; it does not depend on injecting a content script into the browser's native
image preview page.

## Models

Create this layout under `models/`:

```text
models/
  nllb-200-distilled-600M/
  v5/
    PP-OCRv5_server_det/
    PP-OCRv5_server_rec/
    PP-LCNet_x1_0_textline_ori/
  lid.176.bin
```

The three Paddle directories can be copied from the existing installation referenced by the
sample program. Download NLLB on a network-connected machine and transfer the complete snapshot
to the server:

```bash
hf download facebook/nllb-200-distilled-600M \
  --local-dir models/nllb-200-distilled-600M
wget -O models/lid.176.bin \
  https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin
```

The service uses `local_files_only=True`; it never downloads a model at runtime.

The local NLLB snapshot must contain at least `config.json`, `pytorch_model.bin`,
`sentencepiece.bpe.model`, and `special_tokens_map.json`. A complete Hugging Face snapshot also
contains `tokenizer_config.json` and `tokenizer.json`; transfer those files when available. The
slow NLLB tokenizer can normally initialize from SentencePiece without `tokenizer.json`, but the
provided translation smoke test must confirm that against the installed Transformers version.

## Existing Windows lc environment

The local validation interpreter is:

```text
D:\SoftService\miniconda3\envs\lc\python.exe
```

That environment is administrator-owned on the current workstation. Run the following from an
Administrator Command Prompt to install only the missing application packages into that exact
environment:

```bat
D:\PythonProject\builder\image-translator-poc\scripts\install_windows_lc.cmd
```

The script deliberately does not replace PyTorch. Diagnose first:

```bat
D:\SoftService\miniconda3\envs\lc\python.exe scripts\diagnose_environment.py
```

On this workstation the installed `torch 2.8.0+cpu` currently fails to load `torch\lib\shm.dll`.
Repair it with the CPU command printed by the install script for local validation, or install the
official CUDA wheel matching the NVIDIA driver on an actual GPU host. Paddle and PyTorch are kept
as explicit platform prerequisites so `pip install -r requirements.txt` cannot silently replace a
working GPU runtime with a CPU build.

After installation and PyTorch repair, validate each model independently:

```bat
D:\SoftService\miniconda3\envs\lc\python.exe scripts\smoke_ocr.py
D:\SoftService\miniconda3\envs\lc\python.exe scripts\smoke_translation.py
```

Then start the Windows validation service with the pinned interpreter:

```bat
scripts\start_windows_lc.cmd
```

The launcher refuses to start when required modules, Torch, or core NLLB files are unavailable.

## Linux GPU deployment

完整的中文部署步骤、GPU 版本矩阵、预检、离线部署和故障处理见
[`LINUX_GPU_DEPLOYMENT.md`](LINUX_GPU_DEPLOYMENT.md)。下面仅保留快速启动摘要。

Prerequisites:

- NVIDIA driver compatible with the chosen CUDA image.
- Docker Engine, Docker Compose v2, and NVIDIA Container Toolkit.
- Local model directories listed above.

Prepare the dedicated Linux configuration. Do not reuse the Windows `.env` file:

```bash
cp .env.linux.example .env.linux
```

Compose mounts `./models` at `/opt/image-translator/models` and explicitly overrides local Windows
paths and CPU settings with Linux GPU values. Confirm `OCR_PRECISION`; use `fp32` first if the
installed Paddle model or GPU has FP16 compatibility issues.

Build and start:

```bash
python3 scripts/validate_models.py --models models --verify-hashes
docker compose --env-file .env.linux build --pull
docker compose --env-file .env.linux run --rm --no-deps image-translator \
  python3 scripts/check_linux_runtime.py
docker compose --env-file .env.linux up -d
docker compose --env-file .env.linux logs -f image-translator
curl http://127.0.0.1:8080/health
```

The Paddle GPU wheel URL depends on CUDA and Paddle versions. Override the build arguments when
the server uses another supported CUDA runtime:

```bash
PADDLE_INDEX_URL=https://www.paddlepaddle.org.cn/packages/stable/cu118/ \
docker compose build --build-arg PADDLE_VERSION=3.1.1
```

Verify the exact wheel URL against the PaddlePaddle installation guide for the server before
building. PyTorch is installed from its default wheel source by `requirements.txt`; pin it to the
matching CUDA wheel in a controlled deployment if the default resolver does not select one.

## Run without Docker

Use Python 3.10 or 3.11 on Linux. Install the correct PaddlePaddle GPU package first, then:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
python run.py
```

Do not run multiple Uvicorn workers on one GPU during the POC. Model loading happens during app
startup and the health endpoint becomes available only after both models are ready.

## API smoke test

Use an explicit source language when `lid.176.bin` is not configured:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/translate-image \
  -F image=@sample.png \
  -F source_language=en \
  -F target_language=zh \
  -D response-headers.txt \
  -o translated.png
```

Useful response headers:

- `X-Detected-Language`: selected or automatically detected source language.
- `X-Region-Count`: rendered OCR region count.
- `X-Elapsed-Ms`: server-side end-to-end latency.

Interactive API documentation is available at `http://SERVER:8080/docs`.

## Load the browser extension

1. Open `chrome://extensions` in Chrome or `edge://extensions` in Edge.
2. Enable Developer mode.
3. Choose **Load unpacked** and select the `extension` directory.
4. Open the extension popup and set the reachable backend URL, for example
   `http://192.168.1.20:8080`.
5. Select source/target languages. In LLM mode, automatic source detection is performed by the
   LLM; in NLLB mode it needs `lid.176.bin`.
6. Right-click a webpage image or a directly opened HTTP(S) image and choose **Translate this image**.

For a directly opened HTTP(S) attachment such as `http://host/kkPreview/PROD_xxx/0.jpg`, the
extension uses the context-menu URL to fetch the original image and opens the result page after
translation. This avoids the native browser preview page's content-script restriction. If the URL
cannot be fetched by the extension, the fallback is a visible-tab screenshot and may include the
browser preview controls; protected browser pages may reject that screenshot for security reasons.

For an HTTP backend on a corporate network, browser security policy may require allowing insecure
content or serving the API through an internal HTTPS reverse proxy. HTTPS is the recommended shared
server setup.

## Tests

The unit tests do not load OCR or translation models:

```bash
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

For acceptance testing, collect representative images for each target script and record OCR text
accuracy, translation usefulness, region count, and `X-Elapsed-Ms`. A useful initial gate is a
median under five seconds per ordinary image and no unsupported-script OCR failures.

## Next engineering steps

1. Benchmark the local OCR recognition model by script and add language-to-model routing where needed.
2. Group OCR lines into paragraphs before translation, then map them back to layout regions.
3. Improve protected and `blob:` image handling where browser permissions allow it.
4. Add request serialization or a small GPU queue after measuring concurrent internal use.
5. Replace basic inpainting and typography only for image categories where the POC data proves it matters.
