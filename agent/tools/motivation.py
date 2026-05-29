import logging

import httpx
from langchain_core.tools import tool

from config import settings
from db.client import get_client

logger = logging.getLogger(__name__)


@tool
async def send_motivation(telegram_user_id: int) -> str:
    """Сгенерировать персональное мотивационное сообщение на основе профиля и прогресса."""
    from llm.provider import get_llm

    client = await get_client()

    profile_result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    profile = profile_result.data or {}

    # Последний замер прогресса
    user_id = profile.get("id")
    progress_text = ""
    if user_id:
        prog_result = (
            await client.table("progress_logs")
            .select("weight_kg, measured_at")
            .eq("user_id", user_id)
            .order("measured_at", desc=True)
            .limit(2)
            .execute()
        )
        logs = prog_result.data or []
        if len(logs) >= 2:
            delta = round(logs[0]["weight_kg"] - logs[1]["weight_kg"], 1)
            sign = "+" if delta > 0 else ""
            progress_text = f"Последнее изменение веса: {sign}{delta} кг."
        elif len(logs) == 1:
            progress_text = f"Текущий вес: {logs[0]['weight_kg']} кг."

    goal_labels = {
        "lose_weight": "похудение",
        "gain_muscle": "набор мышечной массы",
        "maintain": "поддержание формы",
    }
    goal = goal_labels.get(profile.get("goal", ""), profile.get("goal", ""))

    llm = get_llm()
    prompt = (
        f"Напиши короткое (2-3 предложения) персональное мотивационное сообщение для {profile.get('name', 'пользователя')}.\n"
        f"Цель: {goal}. {progress_text}\n"
        f"Будь вдохновляющим, конкретным, без шаблонных фраз. Отвечай на русском."
    )
    try:
        response = await llm.ainvoke(prompt)
        return response.content or "Ты молодец — продолжай в том же духе! 💪"
    except Exception:
        logger.exception("LLM call failed in send_motivation for user %s", telegram_user_id)
        return "Ты уже сделал шаг вперёд, придя сюда. Продолжай — у тебя всё получится! 💪"


# Доступные шаблоны ImgFlip для мотивационных мемов
_MEME_TEMPLATES = {
    "181913649": "Drake Hotline Bling",     # X плохо / Y хорошо — универсальный
    "101288": "Success Kid",                 # маленькая победа
    "87743020": "Two Buttons",              # выбор между ленью и действием
    "61579": "One Does Not Simply",         # преувеличение трудности
    "14371066": "Most Interesting Man",     # "я не всегда тренируюсь, но когда..."
}


@tool
async def generate_motivation_meme(
    telegram_user_id: int,
    top_text: str,
    bottom_text: str,
    template_id: str = "181913649",
) -> str:
    """Сгенерировать мотивационный мем через ImgFlip API.

    Доступные template_id:
    - "181913649" — Drake Hotline Bling (X плохо / Y хорошо, универсальный)
    - "101288"    — Success Kid (маленькая победа)
    - "87743020"  — Two Buttons (выбор между ленью и действием)
    - "61579"     — One Does Not Simply (преувеличение трудности)
    - "14371066"  — Most Interesting Man

    top_text: текст вверху мема (≤ 40 символов, русский, что пользователь избегает)
    bottom_text: текст внизу мема (≤ 40 символов, русский, что он делает правильно)

    Возвращает строку MEME_IMAGE_URL:https://... которую нужно включить в ответ дословно.
    """
    if not settings.imgflip_username or not settings.imgflip_password:
        logger.info("ImgFlip credentials not configured — skipping meme generation")
        return "MEME_UNAVAILABLE"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.imgflip.com/caption_image",
                data={
                    "template_id": template_id,
                    "username": settings.imgflip_username,
                    "password": settings.imgflip_password,
                    "text0": top_text[:100],
                    "text1": bottom_text[:100],
                },
            )
        data = resp.json()
        if data.get("success"):
            url = data["data"]["url"]
            logger.info("Meme generated for user %s: %s", telegram_user_id, url)
            return f"MEME_IMAGE_URL:{url}"
        logger.warning("ImgFlip API error for user %s: %s", telegram_user_id, data.get("error_message"))
        return "MEME_UNAVAILABLE"
    except Exception:
        logger.exception("generate_motivation_meme failed for user %s", telegram_user_id)
        return "MEME_UNAVAILABLE"
