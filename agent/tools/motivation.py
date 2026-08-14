import logging
import random

import httpx
from langchain_core.tools import tool

from config import settings
from db.client import fetch, fetchrow

logger = logging.getLogger(__name__)


@tool
async def send_motivation(telegram_user_id: int) -> str:
    """Сгенерировать персональное мотивационное сообщение на основе профиля и прогресса."""
    from llm.provider import get_llm

    profile = await fetchrow(
        "SELECT * FROM users WHERE telegram_user_id = $1", telegram_user_id
    )
    profile = profile or {}

    # Последний замер прогресса
    user_id = profile.get("id")
    progress_text = ""
    if user_id:
        logs = await fetch(
            "SELECT weight_kg, measured_at FROM progress_logs "
            "WHERE user_id = $1 ORDER BY measured_at DESC LIMIT 2",
            user_id,
        )
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


# Кэш шаблонов ImgFlip — загружается один раз при первом вызове
_meme_template_ids: list[str] = []


async def _get_meme_template_ids() -> list[str]:
    """Загружает все доступные шаблоны с ImgFlip API и кэширует их."""
    global _meme_template_ids
    if _meme_template_ids:
        return _meme_template_ids

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.imgflip.com/get_memes")
        data = resp.json()
        if data.get("success"):
            _meme_template_ids = [m["id"] for m in data["data"]["memes"]]
            logger.info("ImgFlip: loaded %d meme templates", len(_meme_template_ids))
        else:
            logger.warning("ImgFlip get_memes failed: %s", data)
    except Exception:
        logger.exception("Failed to fetch ImgFlip meme templates")

    # Fallback если API недоступен
    if not _meme_template_ids:
        _meme_template_ids = ["181913649", "101288", "87743020", "61579", "14371066"]

    return _meme_template_ids


@tool
async def generate_motivation_meme(
    telegram_user_id: int,
    top_text: str,
    bottom_text: str,
) -> str:
    """Сгенерировать мотивационный мем через ImgFlip API.

    top_text: текст вверху мема (≤ 40 символов, русский, что пользователь избегает)
    bottom_text: текст внизу мема (≤ 40 символов, русский, что он делает правильно)

    Возвращает строку MEME_IMAGE_URL:https://... которую нужно включить в ответ дословно.
    """
    if not settings.imgflip_username or not settings.imgflip_password:
        logger.info("ImgFlip credentials not configured — skipping meme generation")
        return "MEME_UNAVAILABLE"

    template_ids = await _get_meme_template_ids()
    chosen_template = random.choice(template_ids)
    logger.info("Meme template chosen: %s for user %s", chosen_template, telegram_user_id)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.imgflip.com/caption_image",
                data={
                    "template_id": chosen_template,
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
