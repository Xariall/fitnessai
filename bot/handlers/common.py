"""Общие хендлеры: /start и LLM-чат."""

import asyncio

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.llm_engine import get_llm_response
from bot.database.db import db
from bot.states import Onboarding

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Обработчик команды /start. Автоматически запускает анкету, если профиль не найден."""
    user = await db.get_user(message.from_user.id)

    if user:
        await message.answer(
            f"👋 С возвращением, <b>{message.from_user.first_name}</b>!\n\n"
            "Задай мне любой вопрос о тренировках или питании, "
            "а для обновления профиля нажми /profile 💪",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "👋 Привет! Я — <b>FitnessAI</b>, твой персональный фитнес-помощник.\n\n"
            "Для начала давай настроим твой профиль!\n"
            "Сколько тебе лет? (введи число)\n\n"
            "💡 Ты можешь прервать анкету в любой момент командой /cancel",
            parse_mode="HTML",
        )
        await state.set_state(Onboarding.waiting_for_age)


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

    typing_task = asyncio.create_task(keep_typing())

    try:
        answer = await get_llm_response(message.text)
    finally:
        typing_active = False
        typing_task.cancel()

    await message.answer(answer)
