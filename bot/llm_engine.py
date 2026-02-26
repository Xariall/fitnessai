"""Модуль для работы с LLM через LangChain + Ollama."""

import os
import logging

from langchain_community.llms import Ollama

logger = logging.getLogger(__name__)


def get_llm_response(user_prompt: str) -> str:
    """
    Отправляет запрос в локальную LLM и возвращает сгенерированный текст.
    """
    # Адрес Ollama берём из переменных окружения
    # Внутри Docker-контейнера на Маке: http://host.docker.internal:11434
    ollama_base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # Инициализация модели через LangChain
    llm = Ollama(
        base_url=ollama_base_url,
        model="llama3.1",
    )

    try:
        logger.info(f"Отправка запроса в LLM: {user_prompt[:50]}...")
        response = llm.invoke(user_prompt)
        return response
    except Exception as e:
        logger.error(f"Ошибка при обращении к Ollama: {e}")
        return "🧠 Извини, мои нейроны сейчас перегружены. Попробуй позже!"
