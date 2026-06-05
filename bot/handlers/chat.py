import asyncio
import contextlib
import logging
import re
import time
from io import BytesIO
import json as _json
from typing import Any, Callable, Optional

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from langchain_core.messages import HumanMessage

import agent.graph as _agent_graph_module
from bot.helpers import build_workout_keyboard
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
    "generate_cycle_preview": "🗓 Генерирую черновик программы...",
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
    "generate_motivation_meme": "🎭 Создаю мем...",
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
    on_tool_end: Callable[[str, Any], None] | None = None,
    on_response_msg_id: Callable[[int], None] | None = None,
    state: FSMContext | None = None,
) -> Optional[str]:
    """Unified agent invocation with streaming for both Message and CallbackQuery sources.

    Args:
        source: The triggering Message or CallbackQuery.
        user_text: The user's input to pass to the agent.
        existing_placeholder: Reuse an existing message as the placeholder (e.g. voice status msg).
        keyboard: Inline keyboard to attach to the final response message.
        state: FSMContext for single-message navigation — deletes previous card, tracks new one.
    """
    from bot.budget import increment, is_allowed

    # ── Extract source-specific handles ──────────────────────────────────────
    if isinstance(source, CallbackQuery):
        telegram_user_id = source.from_user.id
        answer_fn = source.message.answer
        answer_photo_fn = source.message.answer_photo
        bot = source.bot
        chat_id = source.message.chat.id
    else:
        telegram_user_id = source.from_user.id
        answer_fn = source.answer
        answer_photo_fn = source.answer_photo
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

    # ── Delete previous card (single-message navigation) ────────────────────
    if state is not None and existing_placeholder is None:
        from bot.helpers import delete_tracked
        await delete_tracked(bot, chat_id, state)

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

            elif kind == "on_tool_end" and on_tool_end is not None:
                tool_name = event.get("name", "")
                output = event.get("data", {}).get("output")
                # LangGraph returns ToolMessage object; extract .content
                if hasattr(output, "content"):
                    output = output.content
                if isinstance(output, str):
                    try:
                        output = _json.loads(output)
                    except Exception:
                        pass
                on_tool_end(tool_name, output)

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

    # Извлекаем URL мема из ответа агента (безопасно, независимо от позиции в тексте)
    meme_url: str | None = None
    match = re.search(r"MEME_IMAGE_URL:(https://\S+)", accumulated)
    if match:
        meme_url = match.group(1)
        accumulated = accumulated.replace(match.group(0), "").strip()

    if not accumulated:
        await _safe_edit(placeholder, "Не удалось получить ответ. Попробуй ещё раз.")
        return None

    if meme_url:
        # Отправляем фото с текстом как caption — одно сообщение вместо двух
        with contextlib.suppress(Exception):
            await placeholder.delete()
        try:
            await answer_photo_fn(
                meme_url,
                caption=accumulated,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
        except TelegramBadRequest:
            # Если Markdown в caption сломался — без форматирования
            await answer_photo_fn(meme_url, caption=accumulated, reply_markup=keyboard)
        except Exception:
            logger.warning("Failed to send meme photo for user %s", telegram_user_id, exc_info=True)
            # Fallback: текст отдельно
            try:
                await answer_photo_fn(meme_url)
            except Exception:
                pass
            await answer_fn(accumulated, parse_mode=ParseMode.MARKDOWN)
    else:
        try:
            await placeholder.edit_text(accumulated, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except TelegramBadRequest:
            await placeholder.edit_text(accumulated, reply_markup=keyboard)

    if on_response_msg_id is not None:
        on_response_msg_id(placeholder.message_id)

    # ── Track final message for single-message navigation ─────────────────
    if state is not None:
        await state.update_data(last_bot_msg_id=placeholder.message_id)

    return accumulated


async def _run_agent_streaming(
    message: Message,
    telegram_user_id: int,
    user_input: str,
    state: FSMContext | None = None,
) -> Optional[str]:
    """Wrapper around run_agent for Message sources with state tracking."""
    from bot.helpers import build_workout_keyboard

    draft_params: dict | None = None

    def _on_tool_end(tool_name: str, output: Any) -> None:
        nonlocal draft_params
        if tool_name == "generate_cycle_preview":
            if isinstance(output, dict) and output.get("status") == "draft_ready":
                draft_params = {
                    "weeks": output.get("weeks"),
                    "sessions_per_week": output.get("sessions_per_week"),
                    "training_type": output.get("training_type"),
                    "equipment": output.get("equipment"),
                    "goal": output.get("goal"),
                    "has_active_cycle": output.get("has_active_cycle", False),
                }

    response = await run_agent(message, user_input, state=state, on_tool_end=_on_tool_end)

    if draft_params is not None and state is not None:
        await state.update_data(cycle_draft_params=draft_params)
        from bot.keyboards.main import cycle_draft_keyboard
        from bot.helpers import send_and_track
        await send_and_track(
            message,
            "_Нажми кнопку чтобы подтвердить или попросить другой вариант:_",
            state,
            reply_markup=cycle_draft_keyboard(),
        )
    elif response and "программа создана" in response.lower():
        from bot.keyboards.main import after_cycle_create_keyboard
        from bot.helpers import send_and_track
        await send_and_track(
            message,
            "Готов начать? Нажми кнопку:",
            state,
            reply_markup=after_cycle_create_keyboard(),
        )
    return response


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
    "🏋️ Тренировка": "🏋️ *Тренировки*",
    "🥗 Питание": ("🥗 *Питание*", nutrition_submenu_keyboard),
    "📊 Прогресс": ("📊 *Прогресс*", progress_submenu_keyboard),
}


@router.message(F.text.in_(_MAIN_MENU_SUBMENUS.keys()))
async def handle_main_menu_section(
    message: Message, state: FSMContext, is_registered: bool = False
) -> None:
    """Кнопки главного меню открывают соответствующие submenus."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.helpers import send_and_track
    if message.text == "🏋️ Тренировка":
        from bot.helpers import get_workout_section
        text, kb = await get_workout_section(message.from_user.id)
        await send_and_track(message, text, state, reply_markup=kb, delete_user_msg=True)
        return
    text, kb_func = _MAIN_MENU_SUBMENUS[message.text]
    await send_and_track(message, text, state, reply_markup=kb_func(), delete_user_msg=True)


@router.message(F.text == "👤 Профиль")
async def handle_main_menu_profile(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    """Кнопка Профиль из главного меню."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    from bot.handlers.commands import get_profile_text
    from bot.helpers import send_and_track
    text = await get_profile_text(telegram_user_id=message.from_user.id)
    await send_and_track(message, text, state, delete_user_msg=True)


@router.message(F.text == "💪 Мотивация")
async def handle_main_menu_motivation(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    """Кнопка Мотивация из главного меню."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return
    with contextlib.suppress(Exception):
        await message.delete()
    await _run_agent_streaming(message, message.from_user.id, "Мотивируй меня", state=state)


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    """Обработчик голосовых сообщений."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    from bot.helpers import delete_tracked
    await delete_tracked(message.bot, message.chat.id, state)
    status_msg = await message.answer("🎙 _Распознаю речь..._", parse_mode=ParseMode.MARKDOWN)
    await state.update_data(last_bot_msg_id=status_msg.message_id)

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
    # НЕ передаём state — status_msg уже трекается, run_agent переиспользует его
    response_text = await run_agent(message, user_input, existing_placeholder=status_msg)

    # Голосовой ответ на голосовое сообщение
    if response_text:
        try:
            audio_bytes = await _generate_tts(response_text)
            if audio_bytes:
                await message.answer_audio(
                    BufferedInputFile(audio_bytes, filename="response.mp3")
                )
        except Exception:
            logger.warning("TTS failed for user %s", message.from_user.id, exc_info=True)


@router.message()
async def handle_message(message: Message, state: FSMContext, is_registered: bool = False) -> None:
    """Основной обработчик текстовых сообщений."""
    if not is_registered:
        await message.answer("Пожалуйста, начни с команды /start для регистрации.")
        return

    user_input = _build_input_with_context(message, message.text or "")
    await _run_agent_streaming(message, message.from_user.id, user_input, state=state)
