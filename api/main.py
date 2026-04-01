"""FastAPI application — FitAgent backend."""

import base64
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage

from api.schemas import ChatRequest, UserProfile
from database.db import init_db, upsert_user, get_user, ensure_user
from agent.graph import get_graph, cleanup
from agent.prompts import SYSTEM_PROMPT

load_dotenv()

logging.getLogger("google.genai").setLevel(logging.ERROR)

logger = logging.getLogger("fitagent")

_first_message: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from database.seed import seed
    await seed()
    yield
    await cleanup()


app = FastAPI(title="FitAgent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


def _extract_text(response: dict) -> str:
    messages = response.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if not getattr(msg, "tool_calls", None):
                content = msg.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict) and "text" in block:
                            parts.append(block["text"])
                    return "\n".join(parts) if parts else str(content)
                return str(content)
    return "Не удалось получить ответ."


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        return "Ошибка: GEMINI_API_KEY невалидный. Проверьте ключ в .env файле."
    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
        return "Квота Gemini API исчерпана. Подождите минуту и попробуйте снова."
    return "Произошла ошибка. Попробуйте ещё раз."


async def _run_agent(user_id: str, user_message: str) -> str:
    await ensure_user(user_id)
    graph = await get_graph()

    new_messages = []
    if user_id not in _first_message:
        new_messages.append(
            SystemMessage(content=SYSTEM_PROMPT.format(user_id=user_id), id="system")
        )
        _first_message.add(user_id)

    new_messages.append(HumanMessage(content=user_message))

    config = {"configurable": {"thread_id": user_id}}
    response = await graph.ainvoke({"messages": new_messages}, config=config)
    return _extract_text(response)


# ── Chat endpoints ──────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        text = await _run_agent(req.user_id, req.message)
        return {"response": text}
    except Exception as e:
        logger.exception("Chat error")
        return {"response": _friendly_error(e)}


@app.post("/api/chat/image")
async def chat_with_image(
    message: str = Form("Что это за блюдо?"),
    user_id: str = Form("default"),
    weight_grams: float = Form(300),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()
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

@app.post("/api/user")
async def create_or_update_user(profile: UserProfile):
    fields = profile.model_dump(exclude={"user_id"}, exclude_none=True)
    user = await upsert_user(profile.user_id, **fields)
    return {"user": user}


@app.get("/api/user/{user_id}")
async def get_user_profile(user_id: str):
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
