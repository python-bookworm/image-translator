#!/usr/bin/env python3
"""Send a simple message to the configured OpenAI-compatible LLM endpoint.

Usage from the project root:
    python scripts/test_llm.py
    python scripts/test_llm.py "请介绍一下你自己"
    python scripts/test_llm.py --env-file /path/to/.env.native "你好"

The script intentionally tests the LLM endpoint directly. It does not load
OCR, PaddleOCR, NLLB, or the FastAPI application.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests


DEFAULT_MESSAGE = "你好"


def load_env_file(path: Path) -> None:
    """Load simple KEY=value entries without overwriting shell variables."""
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid environment entry at {path}:{line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Empty environment key at {path}:{line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, got: {value!r}")


def build_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = env_bool("LLM_USE_ENV_PROXY", False)
    explicit_proxy = os.getenv("LLM_PROXY", "").strip()
    if explicit_proxy:
        session.proxies.update({"http": explicit_proxy, "https": explicit_proxy})
    return session


def test_llm(message: str) -> int:
    base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

    if not base_url:
        raise ValueError("LLM_BASE_URL is empty")
    if not model:
        raise ValueError("LLM_MODEL is empty")

    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
        "stream": False,
    }

    print(f"请求地址: {url}")
    print(f"模型: {model}")
    print(f"系统代理: {'启用' if env_bool('LLM_USE_ENV_PROXY', False) else '禁用'}")
    if os.getenv("LLM_PROXY", "").strip():
        print("显式代理: 已配置")
    print(f"测试消息: {message}")

    started = time.perf_counter()
    try:
        response = build_session().post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - started) * 1000
        print(f"HTTP 状态: {response.status_code}")
        print(f"请求耗时: {elapsed:.0f} ms")
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        print("模型回复:")
        print(content)
        return 0
    except requests.exceptions.ProxyError as exc:
        print(f"代理连接失败: {exc}", file=sys.stderr)
        print(
            "请检查 LLM_USE_ENV_PROXY 和 LLM_PROXY；直连时建议设置 "
            "LLM_USE_ENV_PROXY=false 且 LLM_PROXY=。",
            file=sys.stderr,
        )
    except requests.exceptions.RequestException as exc:
        print(f"LLM 请求失败: {exc}", file=sys.stderr)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        print(f"LLM 返回格式不符合预期: {exc}", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="测试项目配置的 OpenAI 兼容 LLM 接口")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env.native"),
        help="环境配置文件，默认是项目根目录的 .env.native",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default=DEFAULT_MESSAGE,
        help="发送给模型的文本，默认是‘你好’",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        load_env_file(args.env_file)
        return test_llm(args.message)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
