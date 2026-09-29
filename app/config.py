from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8080
    log_level: str = "INFO"

    ocr_det_model_dir: Path = Path("models/PP-OCRv5_server_det")
    ocr_rec_model_dir: Path = Path("models/PP-OCRv5_server_rec")
    ocr_orientation_model_dir: Path = Path("models/PP-LCNet_x1_0_textline_ori")
    ocr_device: str = "gpu:0"
    ocr_precision: str = "fp16"
    ocr_cpu_threads: int = 8
    ocr_warmup: bool = True
    ocr_min_score: float = Field(default=0.45, ge=0, le=1)

    translation_model_dir: Path = Path("models/nllb-200-distilled-600M")
    translation_device: str = "cuda:0"
    translation_dtype: str = "float16"
    translation_batch_size: int = Field(default=16, ge=1, le=128)
    translation_max_input_tokens: int = Field(default=512, ge=32, le=2048)
    translation_max_new_tokens: int = Field(default=256, ge=16, le=1024)
    language_id_model: Path | None = None

    translation_provider: str = "nllb"
    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "default/deepseek-v3-2"
    llm_timeout_seconds: int = Field(default=120, ge=1, le=1200)
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    # Smaller batches reduce JSON truncation on gateways with conservative output limits.
    llm_batch_size: int = Field(default=8, ge=1, le=100)
    llm_max_batch_chars: int = Field(default=1200, ge=100, le=10000)
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    llm_retry_count: int = Field(default=2, ge=0, le=5)
    llm_retry_backoff_seconds: float = Field(default=1.0, ge=0, le=30)
    llm_fallback_to_nllb: bool = True
    # Requests inherits HTTP(S)_PROXY from the shell by default. Keep proxy
    # behavior explicit because internal LLM endpoints often reject proxies.
    llm_use_env_proxy: bool = False
    llm_proxy: str | None = None

    render_font_path: Path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    render_min_font_size: int = 10
    render_max_font_size: int = 64
    render_inpaint_radius: int = 4
    max_image_bytes: int = 20 * 1024 * 1024
    max_image_pixels: int = 40_000_000

    @field_validator("language_id_model", mode="before")
    @classmethod
    def empty_path_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("translation_provider")
    @classmethod
    def valid_translation_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"nllb", "llm"}:
            raise ValueError("TRANSLATION_PROVIDER must be nllb or llm")
        return normalized

    @field_validator("llm_proxy", mode="before")
    @classmethod
    def empty_proxy_is_none(cls, value: object) -> object:
        return None if value is None or str(value).strip() == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
