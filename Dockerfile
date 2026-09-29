ARG CUDA_IMAGE=nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
FROM ${CUDA_IMAGE}

ARG PADDLE_INDEX_URL=https://www.paddlepaddle.org.cn/packages/stable/cu126/
ARG PADDLE_VERSION=3.2.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
ARG TORCH_VERSION=2.7.1

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip fonts-noto-cjk libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/image-translator
COPY requirements.txt .
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install "paddlepaddle-gpu==${PADDLE_VERSION}" --index-url "${PADDLE_INDEX_URL}" \
    && python3 -m pip install "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX_URL}" \
    && python3 -m pip install -r requirements.txt

COPY app app
COPY scripts/validate_models.py scripts/validate_models.py
COPY scripts/check_linux_runtime.py scripts/check_linux_runtime.py
COPY scripts/docker_entrypoint.sh scripts/docker_entrypoint.sh
COPY run.py .
RUN chmod +x scripts/docker_entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1
CMD ["scripts/docker_entrypoint.sh"]
