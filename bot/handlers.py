"""Роутер с обработчиками команд и сообщений."""

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
    """
    # Показываем статус "печатает..."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Отправляем текст в LangChain → Ollama
    answer = get_llm_response(message.text)

    # Возвращаем сгенерированный ответ
    await message.answer(answer)
