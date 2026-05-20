"""Inline-режим: @bot <запрос> в любом чате."""
import uuid

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

router = Router()

# Быстрые действия — пользователь выбирает и текст уходит агенту в личку
_QUICK_ACTIONS = [
    ("📊 Моя статистика", "Покажи мою статистику на сегодня"),
    ("🏋️ Составить тренировку", "Составь тренировку на сегодня"),
    ("🥗 Что поесть?", "Составь план питания на день"),
    ("⚖️ Записать вес", "Хочу записать свой вес"),
    ("💪 Мотивируй меня", "Мотивируй меня"),
    ("🔥 Моя норма КБЖУ", "Какая моя дневная норма калорий и БЖУ?"),
]


@router.inline_query()
async def handle_inline_query(query: InlineQuery) -> None:
    """Обрабатывает @bot <текст> в любом чате.

    Если пользователь ввёл текст — предлагает отправить его агенту.
    Всегда показывает быстрые действия.
    """
    user_input = query.query.strip()
    results: list[InlineQueryResultArticle] = []

    if user_input:
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=f"🤖 Спросить FitnessAI: {user_input[:50]}",
                description="Нажми — текст будет отправлен в этот чат как сообщение боту",
                input_message_content=InputTextMessageContent(
                    message_text=user_input,
                ),
            )
        )

    for title, msg_text in _QUICK_ACTIONS:
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=title,
                description=f'Отправит боту: «{msg_text}»',
                input_message_content=InputTextMessageContent(
                    message_text=msg_text,
                ),
            )
        )

    await query.answer(results, cache_time=0, is_personal=True)
