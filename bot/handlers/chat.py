import asyncio
import contextlib
import logging
import time
from io import BytesIO
from typing import Optional

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from langchain_core.messages import HumanMessage

import agent.graph as _agent_graph_module
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
    "check_recovery_status": "🔄 Проверяю восстановление...",
    "create_training_cycle": "🗓 Создаю тренировочный цикл...",
    "get_active_cycle": "📅 Загружаю программу...",
    "get_next_session_plan": "💪 Готовлю тренировку по программе...",
    "get_cycle_summary": "🏆 Считаю итоги цикла...",
    "get_cycle_by_id": "📋 Загружаю предыдущий цикл...",
    "get_workout_nutrition_protocol": "🥗 Составляю протокол питания...",
    "check_nutrition_adjustment": "📊 Анализирую прогресс питания...",
    "calculate_hydration": "💧 Считаю норму воды...",
    "get_weekly_summary": "📊 Загружаю итог недели...",
    "delete_log_entry": "🗑 Удаляю запись...",
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


async def _generate_tts(text: str) -> bytes:
    """Генерирует MP3-аудио из текста через edge-tts (ru-RU-SvetlanaNeural)."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice="ru-RU-SvetlanaNeural")
    bio = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            bio.write(chunk["data"])
    bio.seek(0)
    return bio.read()


async def run_agent(
    source: Message | CallbackQuery,
    user_text: str,
    *,
    existing_placeholder: Message | None = None,
    keyboard: InlineKeyboardMarkup | None = None,
) -> Optional[str]:
    """Unified agent invocation with streaming for both Message and CallbackQuery sources.

    For CallbackQuery: removes the old inline keyboard from the trigger message before
    sending the placeholder, so the chat stays clean.

    Args:
        source: The triggering Message or CallbackQuery.
        user_text: The user's input to pass to the agent.
        existing_placeholder: Reuse an existing message as the placeholder (e.g. voice status msg).
        keyboard: Inline keyboard to attach to the final response message.
    """
    from bot.budget import increment, is_allowed

    # ── Extract source-specific handles ──────────────────────────────────────
    if isinstance(source, CallbackQuery):
        telegram_user_id = source.from_user.id
        answer_fn = source.message.answer
        bot = source.bot
        chat_id = source.message.chat.id
        # Remove the stale inline keyboard from the button message
        with contextlib.suppress(TelegramBadRequest):
            await source.message.edit_reply_markup(reply_markup=None)
    else:
        telegram_user_id = source.from_user.id
        answer_fn = source.answer
        bot = source.bot
        chat_id = source.chat.id

    # ── Budget check ─────────────────────────────────────────────────────────
    if not is_allowed(telegram_user_id, settings.max_requests_per_day):
        await answer_fn(
            f"⚠️ Дневной лимит запросов ({settings.max_requests_per_day}) исчерпан. "
            "Попробуй завтра!"
        )
        return None
    increment(telegram_user_id)

    # ── Placeholder ───────────────────────────────────────────────────────────
    if existing_placeholder is not None:
        placeholder = existing_placeholder
    else:
        placeholder = await answer_fn("⏳ _Обрабатываю..._", parse_mode=ParseMode.MARKDOWN)

    typing_task = asyncio.create_task(_keep_typing(bot, chat_id))

    # pending — буфер текущего вызова планировщика (сбрасывается если вызван инструмент)
    pending = ""
    accumulated = ""
    last_edit_time = 0.0
    last_edit_len = 0
    # Флаг: текущий вызов планировщика является финальным (инструменты не вызывались)
    is_final_planner = True

    try:
        async for event in _agent_graph_module.agent_graph.astream_events(
            {
                "messages": [HumanMessage(content=user_text)],
                "user_profile": {},
                "telegram_user_id": telegram_user_id,
            },
            config={"configurable": {"thread_id": str(telegram_user_id)}},
            version="v2",
        ):
            kind = event["event"]
            node = event.get("metadata", {}).get("langgraph_node", "")

            # DEBUG: log all model-related events
            if kind in ("on_chat_model_start", "on_chat_model_end", "on_chat_model_stream"):
                if kind == "on_chat_model_stream":
                    _chunk = event["data"].get("chunk")
                    _content = getattr(_chunk, "content", None) if _chunk else None
                    _tcc = getattr(_chunk, "tool_call_chunks", None) if _chunk else None
                    logger.debug(
                        "DBG stream node=%s is_final=%s content_type=%s content=%r tcc=%r",
                        node, is_final_planner, type(_content).__name__,
                        str(_content)[:120] if _content else _content, _tcc,
                    )
                else:
                    logger.debug("DBG event=%s node=%s", kind, node)

            if kind == "on_chat_model_start" and node == "planner":
                pending = ""
                is_final_planner = True

            elif kind == "on_tool_start":
                is_final_planner = False
                pending = ""
                accumulated = ""
                last_edit_len = 0
                tool_name = event.get("name", "")
                status = _TOOL_STATUS.get(tool_name, "⏳ Работаю с данными...")
                await _safe_edit(placeholder, f"_{status}_", parse_mode=ParseMode.MARKDOWN)

            elif kind == "on_chat_model_stream" and node == "planner" and is_final_planner:
                chunk = event["data"].get("chunk")
                if not chunk:
                    continue
                if getattr(chunk, "tool_call_chunks", None):
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

            elif kind == "on_chat_model_end" and node == "planner" and is_final_planner:
                # gemini-2.5-flash (thinking model) отдаёт пустые stream chunks,
                # а реальный текст ответа — только в on_chat_model_end
                if not accumulated:
                    output = event["data"].get("output")
                    if output:
                        out_content = getattr(output, "content", None)
                        if isinstance(out_content, str):
                            accumulated = out_content
                        elif isinstance(out_content, list):
                            accumulated = "".join(
                                p if isinstance(p, str) else p.get("text", "")
                                for p in out_content
                                if isinstance(p, (str, dict))
                            )

    except Exception as exc:
        err_str = str(exc)
        is_quota = "429" in err_str or "ResourceExhausted" in type(exc).__name__ or "quota" in err_str.lower()
        is_no_tools = "does not support tools" in err_str
        is_unavailable = "503" in err_str or "unavailable" in err_str.lower()
        if is_no_tools:
            logger.error("Model does not support tools: %s", err_str)
            user_msg = "Что-то пошло не так. Попробуй снова через секунду."
        elif is_unavailable:
            logger.warning("Gemini 503 for user %s: %s", telegram_user_id, err_str)
            user_msg = "⚠️ AI-сервис временно перегружен. Попробуй через 10–30 секунд."
        elif is_quota:
            if "PerDay" in err_str or "per_day" in err_str.lower():
                user_msg = "⚠️ Дневной лимит AI-запросов исчерпан. Попробуй завтра или подключи платный тариф в Google AI Studio."
            else:
                user_msg = "⚠️ Слишком много запросов — подожди минуту и попробуй снова."
        else:
            logger.exception("Streaming error for user %s", telegram_user_id)
            user_msg = "Что-то пошло не так. Попробуй снова через секунду."
        with contextlib.suppress(Exception):
            await placeholder.edit_text(user_msg)
        return None
    finally:
        typing_task.cancel()

    if not accumulated:
        await _safe_edit(placeholder, "Не удалось получить ответ. Попробуй ещё раз.")
        return None

    try:
        await placeholder.edit_text(accumulated, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    except TelegramBadRequest:
        await placeholder.edit_text(accumulated, reply_markup=keyboard)

    return accumulated


async def _run_agent_streaming(message: Message, telegram_user_id: int, user_input: str) -> Optional[str]:
    """Backward-compat wrapper around run_agent for Message sources."""
    return await run_agent(message, user_input)


async def _transcribe_voice(audio_bytes: bytes) -> str:
    """Транскрибирует голосовое сообщение через Gemini."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
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
        f"🎙 _Распознал:_ «{transcription}»\n\n⏳ _Обрабатываю..._",
        parse_mode=ParseMode.MARKDOWN,
    )
    user_input = _build_input_with_context(message, transcription)
    # Reuse status_msg as the agent placeholder — keeps voice to 1 message total
    response_text = await run_agent(message, user_input, existing_placeholder=status_msg)

    # Голосовой ответ на голосовое сообщение
    if response_text:
        try:
            audio_bytes = await _generate_tts(response_text)
            if audio_bytes:
                # edge-tts возвращает MP3 — используем answer_audio (не answer_voice)
                await message.answer_audio(
                    BufferedInputFile(audio_bytes, filename="response.mp3")
                )
        except Exception:
            logger.warning("TTS failed for user %s", message.from_user.id, exc_info=True)


@router.message()
async def handle_message(message: Message, is_registered: bool = False) -> None:
    """Основной обработчик текстовых сообщений."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    user_input = _build_input_with_context(message, message.text or "")
    await _run_agent_streaming(message, message.from_user.id, user_input)
