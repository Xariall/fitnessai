import logging
from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    logger.info("Using Gemini: %s", settings.gemini_model)
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
    )
