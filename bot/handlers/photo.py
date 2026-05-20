"""Обработчик фото — распознаёт еду через Gemini Vision и предлагает записать КБЖУ."""
import asyncio
import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message

from config import settings

logger = logging.getLogger(__name__)
router = Router()

_FOOD_ANALYSIS_PROMPT = (
    "Ты эксперт по питанию. Определи блюдо или продукт на фото и оцени его КБЖУ.\n"
    "Ответь строго в таком формате (без лишних слов):\n"
    "Блюдо: [название]\n"
    "Порция: [примерный вес в граммах]\n"
    "Калории: [число] ккал\n"
    "Белки: [число]г\n"
    "Жиры: [число]г\n"
    "Углеводы: [число]г\n\n"
    "Если на фото нет еды, ответь одной строкой: 'Еда не обнаружена'"
)


async def _analyze_food_photo(image_bytes: bytes) -> str:
    """Отправляет фото в Gemini Vision и возвращает текстовый анализ."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    image_part = {"mime_type": "image/jpeg", "data": image_bytes}
    response = await asyncio.to_thread(
        model.generate_content,
        [_FOOD_ANALYSIS_PROMPT, image_part],
    )
    return response.text.strip()


@router.message(F.photo)
async def handle_food_photo(message: Message, is_registered: bool = False) -> None:
    """Принимает фото, анализирует еду и передаёт агенту для записи в дневник."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    if settings.llm_provider != "gemini":
        await message.answer(
            "📷 Распознавание фото доступно только в режиме Gemini.\n"
            "_Переключи провайдер: `LLM_PROVIDER=gemini`_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    status_msg = await message.answer("📷 _Анализирую фото..._", parse_mode=ParseMode.MARKDOWN)

    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        bio = BytesIO()
        await message.bot.download_file(file.file_path, destination=bio)
        analysis = await _analyze_food_photo(bio.getvalue())
    except Exception:
        logger.exception("Photo analysis error for user %s", message.from_user.id)
        await status_msg.edit_text("Не удалось проанализировать фото. Попробуй ещё раз.")
        return

    if "Еда не обнаружена" in analysis:
        await status_msg.edit_text(
            "🤷 На фото не нашёл еду. Отправь фото блюда — я определю КБЖУ и запишу."
        )
        return

    await status_msg.edit_text(
        f"📷 *Анализ фото:*\n\n{analysis}\n\n_Записываю в дневник..._",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Передаём агенту — он вызовет log_food с распознанными данными
    from bot.handlers.chat import _run_agent_streaming

    agent_prompt = (
        f"Я сфотографировал еду. Вот анализ фото:\n{analysis}\n\n"
        "Запиши это в мой дневник питания на сегодня, используя данные из анализа."
    )
    await _run_agent_streaming(message, message.from_user.id, agent_prompt)
