import logging
from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Фабрика LLM (singleton). Возвращает модель в зависимости от LLM_PROVIDER."""
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        logger.info("Using Ollama: %s", settings.ollama_model)
        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        logger.info("Using Gemini: %s", settings.gemini_model)
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
