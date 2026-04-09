"""FastAPI — clean API server.

Serves only /api/* routes; the React frontend (fitagentfront) runs separately.
"""

from __future__ import annotations

import base64
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage, SystemMessage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent.graph import cleanup, get_graph
from agent.prompts import SYSTEM_PROMPT
from api.auth import get_current_user, router as auth_router
from api.schemas import ChatRequest, ConversationCreate, UserProfileUpdate, WaitlistSignup
from database.db import (
    add_message,
    add_to_waitlist,
    create_conversation,
    get_and_set_system_msg_flag,
    get_conversation,
    get_conversations,
    get_messages,
    update_conversation_title,
    upsert_user_profile,
)
from database.models import User
from database.seed import seed

load_dotenv()

logging.getLogger("google.genai").setLevel(logging.ERROR)
logger = logging.getLogger("fitagent")

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_IMAGE_MAX_BYTES = 5 * 1024 * 1024


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic (entrypoint.sh runs `alembic upgrade head`).
    # seed() is idempotent — only inserts data if tables are empty.
    await seed()
    yield
    await cleanup()


# ── App factory ───────────────────────────────────────────────────────────────

def _make_app() -> FastAPI:
    allowed_origins = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000"
    ).split(",")

    app = FastAPI(title="FitAgent API", version="2.0.0", lifespan=lifespan)

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_req: Request, _exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse({"detail": "Слишком много запросов. Подождите минуту."}, status_code=429)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(auth_router)
    return app


app = _make_app()
limiter = app.state.limiter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b if isinstance(b, str) else b.get("text", "")
            for b in content
            if isinstance(b, (str, dict))
        ) or str(content)
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


async def _run_agent(user_id: int, conversation_id: int, user_message: str) -> str:
    graph = await get_graph()
    thread_id = str(conversation_id)

    # Inject system prompt only on first message in this conversation
    is_first = await get_and_set_system_msg_flag(conversation_id)

    messages = []
    if is_first:
        messages.append(SystemMessage(
            content=SYSTEM_PROMPT.format(user_id=str(user_id)), id="system"
        ))
    messages.append(HumanMessage(content=user_message))

    config = {"configurable": {"thread_id": thread_id}}
    response = await graph.ainvoke({"messages": messages}, config=config)
    return _extract_text(response)


# ── Conversations ─────────────────────────────────────────────────────────────

@app.post("/api/conversations")
async def create_conv(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
) -> dict:
    conv = await create_conversation(user.id, body.title or "Новый чат")
    return {"id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat()}


@app.get("/api/conversations")
async def list_convs(user: User = Depends(get_current_user)) -> list[dict]:
    return await get_conversations(user.id)


@app.get("/api/conversations/{conv_id}/messages")
async def list_messages(conv_id: int, user: User = Depends(get_current_user)) -> list[dict]:
    conv = await get_conversation(conv_id, user.id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return await get_messages(conv_id)


@app.post("/api/conversations/{conv_id}/chat")
@limiter.limit("20/minute")
async def chat_in_conversation(
    conv_id: int,
    request: Request,
    body: ChatRequest,
    user: User = Depends(get_current_user),
) -> dict:
    conv = await get_conversation(conv_id, user.id)
    if not conv:
        raise HTTPException(404, "Conversation not found")

    await add_message(conv_id, "user", body.message)

    try:
        reply = await _run_agent(user.id, conv_id, body.message)
    except Exception as e:
        logger.exception("Agent error")
        reply = _friendly_error(e)

    await add_message(conv_id, "assistant", reply)

    msgs = await get_messages(conv_id)
    if len(msgs) == 2:
        title = body.message[:50]
        await update_conversation_title(conv_id, title)

    return {"response": reply}


@app.post("/api/conversations/{conv_id}/chat/image")
@limiter.limit("10/minute")
async def chat_with_image(
    conv_id: int,
    request: Request,
    message: str = Form("Что это за блюдо?"),
    weight_grams: float = Form(300),
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    conv = await get_conversation(conv_id, user.id)
    if not conv:
        raise HTTPException(404, "Conversation not found")

    image_bytes = await image.read()
    if image.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Allowed formats: {', '.join(_ALLOWED_IMAGE_TYPES)}")
    if len(image_bytes) > _IMAGE_MAX_BYTES:
        raise HTTPException(413, "Image too large (max 5 MB)")

    image_b64 = base64.b64encode(image_bytes).decode()
    combined = (
        f"{message}\n\n"
        f"[Пользователь отправил фото еды. Вес порции: {weight_grams}г. "
        f"Используй analyze_food_photo с image_base64 и weight_grams={weight_grams}, "
        f"затем запиши результат через log_meal.]\n"
        f"image_base64_data:{image_b64}"
    )

    await add_message(conv_id, "user", message)

    try:
        reply = await _run_agent(user.id, conv_id, combined)
    except Exception as e:
        logger.exception("Agent image error")
        reply = _friendly_error(e)

    await add_message(conv_id, "assistant", reply)
    return {"response": reply}


# ── User profile ──────────────────────────────────────────────────────────────

@app.get("/api/profile")
async def get_profile(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "age": user.age,
        "height": user.height,
        "weight": user.weight,
        "gender": user.gender,
        "activity": user.activity,
        "goal": user.goal,
    }


@app.put("/api/profile")
async def update_profile(
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
) -> dict:
    return await upsert_user_profile(user.id, **body.model_dump(exclude_none=True))


# ── Waitlist ──────────────────────────────────────────────────────────────────

@app.post("/api/waitlist")
async def waitlist_signup(body: WaitlistSignup) -> dict:
    is_new = await add_to_waitlist(body.email, body.name)
    return {
        "success": True,
        "isNew": is_new,
        "message": "Вы добавлены в лист ожидания." if is_new else "Вы уже в листе ожидания.",
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
