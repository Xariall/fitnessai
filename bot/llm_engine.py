"""Модуль для работы с LLM через LangChain + Ollama."""

import asyncio
import os
import logging

from langchain_ollama import OllamaLLM

logger = logging.getLogger(__name__)

# Создаём экземпляр модели один раз (не на каждый запрос)
_llm: OllamaLLM | None = None


def _get_llm() -> OllamaLLM:
    """Ленивая инициализация LLM-клиента (синглтон)."""
    global _llm
    if _llm is None:
        ollama_base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        _llm = OllamaLLM(
            base_url=ollama_base_url,
            model="llama3.1",
        )
        logger.info(f"LLM инициализирован: {ollama_base_url}, model=llama3.1")
    return _llm


def _sync_invoke(prompt: str) -> str:
    """Синхронный вызов LLM (для запуска в потоке)."""
    llm = _get_llm()
    return llm.invoke(prompt)


async def get_llm_response(user_prompt: str) -> str:
    """
    Асинхронно отправляет запрос в локальную LLM.
    Вызов LLM идёт в отдельном потоке, чтобы не блокировать event loop.
    """
    try:
        logger.info(f"Отправка запроса в LLM: {user_prompt[:50]}...")
        response = await asyncio.to_thread(_sync_invoke, user_prompt)
        return response
    except Exception as e:
        logger.error(f"Ошибка при обращении к Ollama: {e}")
        return "🧠 Извини, мои нейроны сейчас перегружены. Попробуй позже!"
