import logging

from langchain_core.tools import tool

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
