import logging
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config import get_settings
from app.languages import LANGUAGES, to_nllb
from app.pipeline import ImageTranslationPipeline

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@lru_cache
def get_pipeline() -> ImageTranslationPipeline:
    return ImageTranslationPipeline(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Loading OCR and translation models")
    get_pipeline()
    logger.info("Image translation service is ready")
    yield


app = FastAPI(title="Local Image Translator", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension|moz-extension)://.*$",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Detected-Language", "X-Region-Count", "X-Elapsed-Ms"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "auto_language_detection": (
            settings.translation_provider == "llm"
            or settings.language_id_model is not None
        ),
        "translation_provider": settings.translation_provider,
    }


@app.get("/v1/languages")
def languages() -> list[dict[str, str]]:
    return [
        {
            "code": language.code,
            "name": language.name,
            "name_zh": language.name_zh,
            "nllb_code": language.nllb_code,
        }
        for language in LANGUAGES
    ]


@app.post("/v1/translate-image", response_class=Response)
def translate_image(
    image: UploadFile = File(...),
    source_language: str = Form("auto"),
    target_language: str = Form("zh"),
    source_url: str | None = Form(None),
) -> Response:
    request_id = uuid.uuid4().hex[:12]
    image_path = source_url or image.filename or "<uploaded image>"
    logger.info(
        "[%s] Translation request received: image_path=%s filename=%s "
        "source_language=%s target_language=%s content_type=%s",
        request_id,
        image_path,
        image.filename,
        source_language,
        target_language,
        image.content_type,
    )
    try:
        if source_language != "auto":
            to_nllb(source_language)
        to_nllb(target_language)
        if target_language == "auto":
            raise ValueError("target_language cannot be auto")
        content = image.file.read()
        logger.info("[%s] Image fetched successfully: bytes=%d", request_id, len(content))
        result = get_pipeline().process(
            content, source_language, target_language, request_id=request_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[%s] Image translation failed", request_id)
        raise HTTPException(status_code=500, detail="Image translation failed") from exc
    logger.info(
        "[%s] Translation request completed: detected_language=%s regions=%d "
        "elapsed_ms=%d result_bytes=%d",
        request_id,
        result.source_language,
        result.region_count,
        result.elapsed_ms,
        len(result.image_png),
    )
    return Response(
        content=result.image_png,
        media_type="image/png",
        headers={
            "X-Detected-Language": result.source_language,
            "X-Region-Count": str(result.region_count),
            "X-Elapsed-Ms": str(result.elapsed_ms),
            "Cache-Control": "no-store",
        },
    )
