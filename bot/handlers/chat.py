import asyncio
import logging
import time
from io import BytesIO

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph
from bot.keyboards.main import (
    main_menu_keyboard,
    nutrition_submenu_keyboard,
    progress_submenu_keyboard,
    workout_submenu_keyboard,
)
from config import settings

logger = logging.getLogger(__name__)
router = Router()

# Редактируем placeholder не чаще раза в N секунд (лимит Telegram ~1 edit/s)
_EDIT_INTERVAL = 0.7
# Минимальный прирост символов для редактирования
_EDIT_THRESHOLD = 20

_TOOL_STATUS: dict[str, str] = {
    "log_food": "🍽 Записываю еду...",
    "get_food_info": "🔍 Ищу информацию о продукте...",
    "get_daily_nutrition_summary": "📊 Загружаю дневник питания...",
    "generate_nutrition_plan": "🥗 Создаю план питания...",
    "calculate_daily_calories": "🔥 Считаю калории...",
    "generate_workout_plan": "💪 Создаю план тренировки...",
    "log_workout": "✅ Записываю тренировку...",
    "get_workout_history": "📋 Загружаю историю тренировок...",
    "find_exercises": "🔍 Ищу упражнения...",
    "log_progress": "⚖️ Сохраняю прогресс...",
    "get_progress_summary": "📈 Загружаю статистику...",
    "get_user_profile": "👤 Загружаю профиль...",
    "update_user_profile": "✏️ Обновляю профиль...",
    "send_motivation": "💫 Готовлю мотивацию...",
}


async def _keep_typing(bot, chat_id: int) -> None:
    """Периодически обновляет typing-индикатор (Telegram сбрасывает через 5 сек)."""
    try:
        while True:
            await bot.send_chat_action(chat_id, "typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def _safe_edit(msg: Message, text: str, parse_mode: str | None = None) -> None:
    try:
        await msg.edit_text(text, parse_mode=parse_mode)
    except TelegramBadRequest:
        pass
    except Exception:
        pass


async def _run_agent_streaming(message: Message, telegram_user_id: int, user_input: str) -> None:
    """Запускает агента: показывает статус инструментов, финальный ответ — стримингом."""
    placeholder = await message.answer("⏳ _Обрабатываю..._", parse_mode=ParseMode.MARKDOWN)
    typing_task = asyncio.create_task(_keep_typing(message.bot, message.chat.id))

    # pending — буфер текущего вызова планировщика (сбрасывается если вызван инструмент)
    pending = ""
    accumulated = ""
    last_edit_time = 0.0
    last_edit_len = 0
    # Флаг: текущий вызов планировщика является финальным (инструменты не вызывались)
    is_final_planner = True

    try:
        async for event in agent_graph.astream_events(
            {
                "messages": [HumanMessage(content=user_input)],
                "user_profile": {},
                "telegram_user_id": telegram_user_id,
            },
            config={"configurable": {"thread_id": str(telegram_user_id)}},
            version="v2",
        ):
            kind = event["event"]
            node = event.get("metadata", {}).get("langgraph_node", "")

            if kind == "on_chat_model_start" and node == "planner":
                # Новый вызов планировщика — сбрасываем буфер
                pending = ""
                is_final_planner = True

            elif kind == "on_tool_start":
                # Планировщик решил вызвать инструмент — этот вызов НЕ финальный
                is_final_planner = False
                pending = ""
                accumulated = ""
                last_edit_len = 0
                tool_name = event.get("name", "")
                status = _TOOL_STATUS.get(tool_name, "⏳ Работаю с данными...")
                await _safe_edit(placeholder, f"_{status}_", parse_mode=ParseMode.MARKDOWN)

            elif kind == "on_chat_model_stream" and node == "planner" and is_final_planner:
                chunk = event["data"].get("chunk")
                if not chunk or getattr(chunk, "tool_call_chunks", None):
                    # tool_call chunk — значит это НЕ финальный ответ, сбрасываем
                    is_final_planner = False
                    pending = ""
                    continue

                content = chunk.content
                if isinstance(content, str):
                    text_part = content
                elif isinstance(content, list):
                    text_part = "".join(
                        p if isinstance(p, str) else p.get("text", "")
                        for p in content
                        if isinstance(p, (str, dict))
                    )
                else:
                    continue

                if not text_part:
                    continue

                pending += text_part
                accumulated = pending
                now = time.monotonic()
                new_chars = len(accumulated) - last_edit_len

                if new_chars >= _EDIT_THRESHOLD and now - last_edit_time >= _EDIT_INTERVAL:
                    await _safe_edit(
                        placeholder, accumulated + " ▌", parse_mode=ParseMode.MARKDOWN
                    )
                    last_edit_time = now
                    last_edit_len = len(accumulated)

    except Exception:
        logger.exception("Streaming error for user %s", telegram_user_id)
        try:
            await placeholder.edit_text("Произошла ошибка при обработке запроса. Попробуй ещё раз.")
        except Exception:
            pass
        return
    finally:
        typing_task.cancel()

    if not accumulated:
        await _safe_edit(placeholder, "Не удалось получить ответ. Попробуй ещё раз.")
        return

    try:
        await placeholder.edit_text(accumulated, parse_mode=ParseMode.MARKDOWN)
    except TelegramBadRequest:
        await placeholder.edit_text(accumulated)


async def _transcribe_voice(audio_bytes: bytes) -> str:
    """Транскрибирует голосовое сообщение через Gemini."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    audio_part = {"mime_type": "audio/ogg", "data": audio_bytes}
    response = await asyncio.to_thread(
        model.generate_content,
        [
            "Транскрибируй это голосовое сообщение точно, как есть. "
            "Верни только текст без каких-либо комментариев.",
            audio_part,
        ],
    )
    return response.text.strip()


def _build_input_with_context(message: Message, user_text: str) -> str:
    """Если пользователь ответил на сообщение бота — добавляем цитату как контекст."""
    reply = message.reply_to_message
    if not reply:
        return user_text

    # Проверяем что цитируется сообщение от бота
    if not (reply.from_user and reply.from_user.is_bot):
        return user_text

    quoted = (reply.text or reply.caption or "").strip()
    if not quoted:
        return user_text

    # Обрезаем длинные цитаты чтобы не раздувать контекст
    if len(quoted) > 800:
        quoted = quoted[:800] + "..."

    return (
        f"Контекст (моё предыдущее сообщение):\n{quoted}\n\n"
        f"Запрос пользователя: {user_text}"
    )


_MAIN_MENU_SUBMENUS = {
    "🏋️ Тренировка": ("🏋️ *Тренировки*", workout_submenu_keyboard),
    "🥗 Питание": ("🥗 *Питание*", nutrition_submenu_keyboard),
    "📊 Прогресс": ("📊 *Прогресс*", progress_submenu_keyboard),
}


@router.message(F.text.in_(_MAIN_MENU_SUBMENUS.keys()))
async def handle_main_menu_section(message: Message, is_registered: bool = False) -> None:
    """Кнопки главного меню открывают соответствующие submenus."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    text, kb_func = _MAIN_MENU_SUBMENUS[message.text]
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_func())


@router.message(F.text == "👤 Профиль")
async def handle_main_menu_profile(message: Message, is_registered: bool = False) -> None:
    """Кнопка Профиль из главного меню."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.handlers.commands import _show_profile
    await _show_profile(message)


@router.message(F.text == "💪 Мотивация")
async def handle_main_menu_motivation(message: Message, is_registered: bool = False) -> None:
    """Кнопка Мотивация из главного меню."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    await _run_agent_streaming(message, message.from_user.id, "Мотивируй меня")


@router.message(F.voice)
async def handle_voice(message: Message, is_registered: bool = False) -> None:
    """Обработчик голосовых сообщений."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    if settings.llm_provider != "gemini":
        await message.answer("🎙 Голосовой ввод доступен только в режиме Gemini.")
        return

    status_msg = await message.answer("🎙 _Распознаю речь..._", parse_mode=ParseMode.MARKDOWN)

    try:
        file = await message.bot.get_file(message.voice.file_id)
        bio = BytesIO()
        await message.bot.download_file(file.file_path, destination=bio)
        transcription = await _transcribe_voice(bio.getvalue())
    except Exception:
        logger.exception("Voice transcription error for user %s", message.from_user.id)
        await status_msg.edit_text("Не удалось распознать голосовое сообщение. Попробуй ещё раз.")
        return

    await status_msg.edit_text(
        f"🎙 _Распознал:_ «{transcription}»", parse_mode=ParseMode.MARKDOWN
    )
    user_input = _build_input_with_context(message, transcription)
    await _run_agent_streaming(message, message.from_user.id, user_input)


@router.message()
async def handle_message(message: Message, is_registered: bool = False) -> None:
    """Основной обработчик текстовых сообщений."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    user_input = _build_input_with_context(message, message.text or "")
    await _run_agent_streaming(message, message.from_user.id, user_input)
