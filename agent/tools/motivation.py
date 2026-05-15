import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def send_motivation(telegram_user_id: int) -> str:
    """Сгенерировать персональное мотивационное сообщение на основе профиля и прогресса."""
    # TODO: реализовать генерацию через LLM с данными профиля и прогресса
    raise NotImplementedError
