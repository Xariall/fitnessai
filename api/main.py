"""FastAPI application — FitAgent backend."""

import base64
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, SystemMessage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent.graph import cleanup, get_graph
from agent.prompts import SYSTEM_PROMPT
from api.schemas import ChatRequest, UserProfile
from database.db import (
    ensure_user, get_user, has_system_message_flag,
    init_db, set_system_message_flag, upsert_user,
)

load_dotenv()

logging.getLogger("google.genai").setLevel(logging.ERROR)
logger = logging.getLogger("fitagent")

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_USER_ID_RE = re.compile(r"^[\w\-]+$")

WEB_DIR = Path(__file__).parent.parent / "web"
limiter = Limiter(key_func=get_remote_address)


# ── Auth ─────────────────────────────────────────────────────────────────

def _require_auth(x_api_secret: str = Header(default="")) -> None:
    expected = os.getenv("API_SECRET", "")
    if not expected:
        return
    if x_api_secret != expected:
        raise HTTPException(401, "Invalid or missing API secret")


# ── App factory ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from database.seed import seed
    await seed()
    yield
    await cleanup()


def _rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        {"response": "Слишком много запросов. Подождите минуту."},
        status_code=429,
    )


def _make_app() -> FastAPI:
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")
    application = FastAPI(title="FitAgent API", lifespan=lifespan)
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Api-Secret"],
    )
    if WEB_DIR.exists():
        application.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    return application


app = _make_app()


# ── Helpers ──────────────────────────────────────────────────────────────

def _extract_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block if isinstance(block, str) else block.get("text", "")
            for block in content
            if isinstance(block, (str, dict))
        ]
        return "\n".join(p for p in parts if p) or str(content)
    return str(content)


def _extract_text(response: dict) -> str:
    for msg in reversed(response.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if not getattr(msg, "tool_calls", None):
                return _extract_content(msg.content)
    return "Не удалось получить ответ."


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        return "Ошибка: GEMINI_API_KEY невалидный. Проверьте ключ в .env файле."
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        return "Квота Gemini API исчерпана. Подождите минуту и попробуйте снова."
    return "Произошла ошибка. Попробуйте ещё раз."


def _validated_user_id(raw: str) -> str:
    raw = raw.strip()[:64]
    if not raw or not _USER_ID_RE.match(raw):
        raise HTTPException(400, "Недопустимый user_id")
    return raw


async def _build_messages(user_id: str, user_message: str) -> list:
    messages = []
    if not await has_system_message_flag(user_id):
        messages.append(SystemMessage(content=SYSTEM_PROMPT.format(user_id=user_id), id="system"))
        await set_system_message_flag(user_id)
    messages.append(HumanMessage(content=user_message))
    return messages


async def _run_agent(user_id: str, user_message: str) -> str:
    await ensure_user(user_id)
    graph = await get_graph()
    messages = await _build_messages(user_id, user_message)
    config = {"configurable": {"thread_id": user_id}}
    response = await graph.ainvoke({"messages": messages}, config=config)
    return _extract_text(response)


def _validate_image(image: UploadFile, image_bytes: bytes) -> None:
    if image.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Разрешены только форматы: {', '.join(_ALLOWED_IMAGE_TYPES)}")
    if len(image_bytes) > _IMAGE_MAX_BYTES:
        raise HTTPException(413, "Изображение слишком большое (макс. 5 МБ)")


# ── Chat endpoints ──────────────────────────────────────────────────────

@app.post("/api/chat", dependencies=[Depends(_require_auth)])
@limiter.limit("20/minute")
async def chat(request: Request, req: ChatRequest):
    try:
        text = await _run_agent(req.user_id, req.message)
        return {"response": text}
    except Exception as e:
        logger.exception("Chat error")
        return {"response": _friendly_error(e)}


@app.post("/api/chat/image", dependencies=[Depends(_require_auth)])
@limiter.limit("10/minute")
async def chat_with_image(
    request: Request,
    message: str = Form("Что это за блюдо?"),
    user_id: str = Form("default"),
    weight_grams: float = Form(300),
    image: UploadFile = File(...),
):
    user_id = _validated_user_id(user_id)
    image_bytes = await image.read()
    _validate_image(image, image_bytes)

    image_b64 = base64.b64encode(image_bytes).decode()
    combined_message = (
        f"{message}\n\n"
        f"[Пользователь отправил фото еды. Вес порции: {weight_grams}г. "
        f"Используй tool analyze_food_photo с параметрами image_base64 и weight_grams={weight_grams}, "
        f"затем запиши результат в дневник через log_meal.]\n"
        f"image_base64_data:{image_b64}"
    )

    try:
        text = await _run_agent(user_id, combined_message)
        return {"response": text}
    except Exception as e:
        logger.exception("Image chat error")
        return {"response": _friendly_error(e)}


# ── User profile ────────────────────────────────────────────────────────

@app.post("/api/user", dependencies=[Depends(_require_auth)])
async def create_or_update_user(profile: UserProfile):
    fields = profile.model_dump(exclude={"user_id"}, exclude_none=True)
    user = await upsert_user(profile.user_id, **fields)
    return {"user": user}


@app.get("/api/user/{user_id}", dependencies=[Depends(_require_auth)])
async def get_user_profile(user_id: str):
    user_id = _validated_user_id(user_id)
    user = await get_user(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"user": user}


# ── Web UI ──────────────────────────────────────────────────────────────

@app.get("/")
async def serve_ui():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "FitAgent API is running. Web UI not found."}
