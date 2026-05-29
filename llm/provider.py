import logging
from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Без thinking — для базовых запросов и первичного планирования (быстро)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    logger.info("Using Gemini (no thinking): %s", settings.gemini_model)
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        thinking_budget=0,
    )


@lru_cache(maxsize=1)
def get_llm_thinking() -> BaseChatModel:
    """С thinking — для синтеза результатов инструментов (качественный ответ)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    logger.info(
        "Using Gemini (thinking budget=%d): %s",
        settings.thinking_budget,
        settings.gemini_model,
    )
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        thinking_budget=settings.thinking_budget,
    )
