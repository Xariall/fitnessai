"""Роутер с обработчиками команд и сообщений."""

import asyncio

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.llm_engine import get_llm_response

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start."""
    await message.answer(
        "👋 Привет! Я — <b>FitnessAI</b>, твой персональный фитнес-помощник.\n\n"
        "Я помогу тебе с тренировками, питанием и ответами на вопросы о здоровом образе жизни.\n\n"
        "Просто напиши мне, и мы начнём! 💪",
        parse_mode="HTML",
    )


@router.message(F.text)
async def chat_with_llm(message: Message) -> None:
    """
    Ловит весь текст (кроме команд) и отправляет в Llama 3.1 через Ollama.
    Показывает «печатает...» каждые 4 секунды, пока модель генерирует ответ.
    """
    typing_active = True

    async def keep_typing() -> None:
        """Периодически отправляет typing-статус, пока LLM думает."""
        while typing_active:
            await message.bot.send_chat_action(
                chat_id=message.chat.id, action="typing"
            )
            await asyncio.sleep(4)

    # Запускаем typing в фоне
    typing_task = asyncio.create_task(keep_typing())

    try:
        # Асинхронный вызов LLM (не блокирует event loop)
        answer = await get_llm_response(message.text)
    finally:
        typing_active = False
        typing_task.cancel()

    await message.answer(answer)
