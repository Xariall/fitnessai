"""Прямые ответы без LLM — чтение БД + форматирование."""
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, Message

from agent.constants import ACTIVITY_MULTIPLIERS as _ACTIVITY_MULTIPLIERS, GOAL_ADJUSTMENTS as _GOAL_ADJUSTMENTS
from bot.helpers import build_workout_keyboard
from bot.keyboards.main import (
    after_nutrition_keyboard,
    after_progress_keyboard,
    after_stats_keyboard,
    after_weight_keyboard,
    after_workout_keyboard,
    nutrition_submenu_keyboard,
    progress_submenu_keyboard,
    workout_submenu_keyboard,
)
from bot.helpers import get_cycle_banner
from db.client import get_client

logger = logging.getLogger(__name__)
router = Router()

_MEAL_LABELS = {
    "breakfast": "Завтрак",
    "lunch": "Обед",
    "dinner": "Ужин",
    "snack": "Перекус",
}


def _progress_bar(consumed: float, norm: float, width: int = 10) -> str:
    pct = min(consumed / norm * 100, 100) if norm > 0 else 0
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _pct(consumed: float, norm: float) -> int:
    return min(int(consumed / norm * 100), 100) if norm > 0 else 0


async def _get_user(telegram_user_id: int) -> Optional[dict]:
    client = await get_client()
    result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    return result.data


def _calc_norms(user: dict) -> dict:
    bmr = 10 * user["weight_kg"] + 6.25 * user["height_cm"] - 5 * user["age"] + 5
    tdee = bmr * _ACTIVITY_MULTIPLIERS.get(user.get("activity_level", "moderate"), 1.55)
    calories = int(tdee + _GOAL_ADJUSTMENTS.get(user.get("goal", "maintain"), 0))
    protein = round(user["weight_kg"] * 2.0, 1)
    fat = round(calories * 0.25 / 9)
    carbs = round((calories - protein * 4 - fat * 9) / 4)
    return {"calories": calories, "protein": protein, "fat": fat, "carbs": carbs}


async def _send(message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


# ──────────────────────────────────────────────
# Итог питания за сегодня
# ──────────────────────────────────────────────

async def show_today_summary(message: Message, telegram_user_id: int) -> None:
    try:
        user = await _get_user(telegram_user_id)
        if not user:
            await message.answer("Профиль не найден. Начни с /start.")
            return

        client = await get_client()
        today = date.today().isoformat()
        logs_result = (
            await client.table("food_logs")
            .select("calories, protein, fat, carbs")
            .eq("user_id", user["id"])
            .gte("logged_at", f"{today}T00:00:00")
            .execute()
        )
        logs = logs_result.data or []
        norms = _calc_norms(user)

        if not logs:
            await _send(
                message,
                "🍽 *Итог за сегодня*\n\n"
                "Пока ничего не записано.\n"
                "_Напиши что ел — я посчитаю!_",
                reply_markup=after_nutrition_keyboard(),
            )
            return

        c = {
            "calories": sum(r["calories"] for r in logs),
            "protein": round(sum(r["protein"] for r in logs), 1),
            "fat": round(sum(r["fat"] for r in logs), 1),
            "carbs": round(sum(r["carbs"] for r in logs), 1),
        }
        n = norms

        remaining = n["calories"] - c["calories"]
        if remaining <= 0:
            hint = f"_День закрыт! {c['calories']} ккал — отличная работа 🎯_"
        else:
            hint = f"_Ещё ~{remaining} ккал до нормы._"

        text = (
            "🍽 *Итог за сегодня*\n\n"
            f"Калории:  `{c['calories']} / {n['calories']} ккал` {_progress_bar(c['calories'], n['calories'])} {_pct(c['calories'], n['calories'])}%\n"
            f"Белки:    `{c['protein']} / {n['protein']}г` {_progress_bar(c['protein'], n['protein'])} {_pct(c['protein'], n['protein'])}%\n"
            f"Жиры:     `{c['fat']} / {n['fat']}г` {_progress_bar(c['fat'], n['fat'])} {_pct(c['fat'], n['fat'])}%\n"
            f"Углеводы: `{c['carbs']} / {n['carbs']}г` {_progress_bar(c['carbs'], n['carbs'])} {_pct(c['carbs'], n['carbs'])}%\n\n"
            f"{hint}"
        )
        await _send(message, text, reply_markup=after_nutrition_keyboard())

    except Exception:
        logger.exception("show_today_summary error for user %s", telegram_user_id)
        await message.answer("Не удалось загрузить данные. Попробуй ещё раз.")


# ──────────────────────────────────────────────
# История тренировок
# ──────────────────────────────────────────────

async def show_workout_history(message: Message, telegram_user_id: int) -> None:
    try:
        user = await _get_user(telegram_user_id)
        if not user:
            await message.answer("Профиль не найден. Начни с /start.")
            return

        client = await get_client()
        result = (
            await client.table("workout_logs")
            .select("notes, completed_at, workouts(title)")
            .eq("user_id", user["id"])
            .order("completed_at", desc=True)
            .limit(5)
            .execute()
        )
        logs = result.data or []

        banner = await get_cycle_banner(user["id"])

        if not logs:
            prefix = banner or ""
            await _send(
                message,
                f"{prefix}📋 *История тренировок*\n\n"
                "Тренировок пока нет.\n"
                "_Напиши «запиши тренировку» после занятия!_",
                reply_markup=after_workout_keyboard(),
            )
            return

        lines = [banner, "📋 *История тренировок*\n"] if banner else ["📋 *История тренировок*\n"]
        for i, log in enumerate(logs, 1):
            dt = datetime.fromisoformat(log["completed_at"].replace("Z", "+00:00"))
            date_str = dt.astimezone().strftime("%-d %b")
            title = log.get("workouts", {}).get("title") if log.get("workouts") else None
            notes = log.get("notes", "")

            if title:
                lines.append(f"{i}. *{title}* · {date_str}")
            else:
                lines.append(f"{i}. *Тренировка* · {date_str}")

            if notes:
                short = notes[:80] + ("..." if len(notes) > 80 else "")
                lines.append(f"   _{short}_")

        await _send(message, "\n".join(lines), reply_markup=after_workout_keyboard())

    except Exception:
        logger.exception("show_workout_history error for user %s", telegram_user_id)
        await message.answer("Не удалось загрузить историю. Попробуй ещё раз.")


# ──────────────────────────────────────────────
# Динамика веса
# ──────────────────────────────────────────────

async def show_progress_dynamics(message: Message, telegram_user_id: int) -> None:
    try:
        user = await _get_user(telegram_user_id)
        if not user:
            await message.answer("Профиль не найден. Начни с /start.")
            return

        client = await get_client()
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        result = (
            await client.table("progress_logs")
            .select("weight_kg, measured_at")
            .eq("user_id", user["id"])
            .gte("measured_at", since)
            .order("measured_at", desc=True)
            .limit(10)
            .execute()
        )
        logs = result.data or []

        if not logs:
            await _send(
                message,
                "📊 *Динамика веса*\n\n"
                "Замеров пока нет.\n"
                "_Запиши свой вес: нажми «Записать замер» или напиши «вешу 80кг»_",
                reply_markup=after_progress_keyboard(),
            )
            return

        latest = logs[0]["weight_kg"]
        oldest = logs[-1]["weight_kg"]
        delta = round(latest - oldest, 1)
        sign = "+" if delta > 0 else ""
        trend = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")

        lines = [
            "📊 *Динамика веса*\n",
            f"{trend} *{sign}{delta} кг* за последние 30 дней\n",
        ]
        for log in logs:
            dt = datetime.fromisoformat(log["measured_at"].replace("Z", "+00:00"))
            date_str = dt.astimezone().strftime("%-d %b")
            lines.append(f"• {date_str} — {log['weight_kg']} кг")

        await _send(message, "\n".join(lines), reply_markup=after_progress_keyboard())

    except Exception:
        logger.exception("show_progress_dynamics error for user %s", telegram_user_id)
        await message.answer("Не удалось загрузить данные. Попробуй ещё раз.")


# ──────────────────────────────────────────────
# Общая статистика (/stats)
# ──────────────────────────────────────────────

def _days_word(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return "дней"
    r = n % 10
    if r == 1:
        return "день"
    if 2 <= r <= 4:
        return "дня"
    return "дней"


async def show_stats(message: Message, telegram_user_id: int) -> None:
    try:
        user = await _get_user(telegram_user_id)
        if not user:
            await message.answer("Профиль не найден. Начни с /start.")
            return

        client = await get_client()
        today = date.today().isoformat()
        week_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        norms = _calc_norms(user)

        # Калории за сегодня
        today_food = (
            await client.table("food_logs")
            .select("calories")
            .eq("user_id", user["id"])
            .gte("logged_at", f"{today}T00:00:00")
            .execute()
        ).data or []
        today_calories = int(sum(r["calories"] for r in today_food))

        # Тренировки сегодня
        today_workouts = (
            await client.table("workout_logs")
            .select("id")
            .eq("user_id", user["id"])
            .gte("completed_at", f"{today}T00:00:00")
            .execute()
        ).data or []
        today_workout_count = len(today_workouts)

        # Тренировки за неделю
        week_workouts = (
            await client.table("workout_logs")
            .select("id")
            .eq("user_id", user["id"])
            .gte("completed_at", week_start)
            .execute()
        ).data or []
        week_workout_count = len(week_workouts)

        # Среднее КБЖУ за неделю (по дням)
        week_food = (
            await client.table("food_logs")
            .select("calories, logged_at")
            .eq("user_id", user["id"])
            .gte("logged_at", week_start)
            .execute()
        ).data or []
        days_calories: dict[str, int] = {}
        for row in week_food:
            day = row["logged_at"][:10]
            days_calories[day] = days_calories.get(day, 0) + int(row["calories"])
        avg_calories = int(sum(days_calories.values()) / len(days_calories)) if days_calories else 0

        # Динамика веса за неделю
        weight_logs = (
            await client.table("progress_logs")
            .select("weight_kg, measured_at")
            .eq("user_id", user["id"])
            .gte("measured_at", week_start)
            .order("measured_at")
            .execute()
        ).data or []

        weight_line = ""
        if len(weight_logs) >= 2:
            w_start = weight_logs[0]["weight_kg"]
            w_end = weight_logs[-1]["weight_kg"]
            delta = round(w_end - w_start, 1)
            sign = "+" if delta > 0 else ""
            weight_line = f"• Вес: {w_start} → {w_end} кг ({sign}{delta} кг)\n"
        elif user.get("weight_kg"):
            weight_line = f"• Вес: {user['weight_kg']} кг\n"

        # Дней в приложении
        days_in_app = 0
        created_raw = user.get("created_at", "")
        if created_raw:
            try:
                created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                days_in_app = max((datetime.now(timezone.utc) - created_dt).days, 1)
            except Exception:
                pass

        cal_pct = _pct(today_calories, norms["calories"])
        avg_line = f"• Средние калории: {avg_calories} ккал/день\n" if avg_calories else ""

        from bot.budget import get_count, get_remaining
        from config import settings as cfg
        request_count = get_count(telegram_user_id)
        remaining = get_remaining(telegram_user_id, cfg.max_requests_per_day)
        if cfg.max_requests_per_day > 0:
            budget_line = f"\n_Запросов сегодня: {request_count} / {cfg.max_requests_per_day} (осталось: {remaining})_"
        else:
            budget_line = f"\n_Запросов сегодня: {request_count}_"

        text = (
            "📊 *Твоя статистика*\n\n"
            "*Сегодня:*\n"
            f"• Калории: {today_calories} / {norms['calories']} ккал ({cal_pct}%) {_progress_bar(today_calories, norms['calories'], 8)}\n"
            f"• Тренировок: {today_workout_count}\n\n"
            "*Эта неделя:*\n"
            f"• Тренировок: {week_workout_count}\n"
            f"{avg_line}"
            f"{weight_line}\n"
            f"*С начала:* {days_in_app} {_days_word(days_in_app)} в приложении 🔥"
            f"{budget_line}"
        )
        await _send(message, text, reply_markup=after_stats_keyboard())

    except Exception:
        logger.exception("show_stats error for user %s", telegram_user_id)
        await message.answer("Не удалось загрузить статистику. Попробуй ещё раз.")


# ──────────────────────────────────────────────
# FSM: Запись замера веса
# ──────────────────────────────────────────────

class WeightFSM(StatesGroup):
    waiting_for_weight = State()


_MENU_SUBMENUS = {
    "🏋️ Тренировка": "🏋️ *Тренировки*",
    "🥗 Питание": ("🥗 *Питание*", nutrition_submenu_keyboard),
    "📊 Прогресс": ("📊 *Прогресс*", progress_submenu_keyboard),
}
_MENU_ALL = frozenset({*_MENU_SUBMENUS.keys(), "👤 Профиль", "💪 Мотивация"})


@router.message(WeightFSM.waiting_for_weight, F.text.in_(_MENU_ALL))
async def weight_fsm_escape(message: Message, state: FSMContext) -> None:
    """Кнопки главного меню выходят из FSM без потери нажатия."""
    await state.clear()
    text = message.text or ""
    if text == "🏋️ Тренировка":
        kb = await build_workout_keyboard(message.from_user.id)
        await message.answer("🏋️ *Тренировки*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    elif text in _MENU_SUBMENUS:
        title, kb_func = _MENU_SUBMENUS[text]
        await message.answer(title, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_func())
    else:
        # Профиль и Мотивация — просто сбрасываем, следующее нажатие сработает
        await message.answer("Ввод веса отменён. Нажми кнопку ещё раз 👇")


@router.message(WeightFSM.waiting_for_weight)
async def handle_weight_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").replace(",", ".").strip()
    try:
        weight = float(text)
    except ValueError:
        await message.answer("Введи вес числом, например: `82.5`", parse_mode=ParseMode.MARKDOWN)
        return

    await state.clear()
    telegram_user_id = message.from_user.id

    try:
        user = await _get_user(telegram_user_id)
        if not user:
            await message.answer("Профиль не найден. Начни с /start.")
            return

        client = await get_client()

        prev_result = (
            await client.table("progress_logs")
            .select("weight_kg")
            .eq("user_id", user["id"])
            .order("measured_at", desc=True)
            .limit(1)
            .execute()
        )
        prev = prev_result.data[0]["weight_kg"] if prev_result.data else None

        await client.table("progress_logs").insert({
            "user_id": user["id"],
            "weight_kg": weight,
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        await client.table("users").update({"weight_kg": weight}).eq("telegram_user_id", telegram_user_id).execute()

        today_str = datetime.now().strftime("%-d %B %Y")

        if prev is not None:
            delta = round(weight - prev, 1)
            sign = "+" if delta > 0 else ""
            trend = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
            delta_line = f"{trend} {sign}{delta} кг с прошлого замера"
        else:
            delta_line = "Первый замер — точка отсчёта!"

        await _send(
            message,
            f"📊 *Прогресс записан*\n\n"
            f"Вес: `{weight} кг`\n"
            f"{delta_line}\n"
            f"Дата: {today_str}\n\n"
            "_Держи темп! 💪_",
            reply_markup=after_weight_keyboard(),
        )

    except Exception:
        logger.exception("handle_weight_input error for user %s", telegram_user_id)
        await message.answer("Не удалось сохранить замер. Попробуй ещё раз.")


# ──────────────────────────────────────────────
# FSM: Ввод еды / тренировки через кнопку
# ──────────────────────────────────────────────

class InputModeFSM(StatesGroup):
    waiting_for_input = State()


_INPUT_TIMEOUT_SEC = 900  # 15 минут


@router.message(InputModeFSM.waiting_for_input, F.text.in_(_MENU_ALL))
async def input_mode_escape(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = message.text or ""
    if text in _MENU_SUBMENUS:
        title, kb_func = _MENU_SUBMENUS[text]
        await message.answer(title, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_func())
    else:
        await message.answer("Ввод отменён. Нажми кнопку ещё раз 👇")


@router.message(InputModeFSM.waiting_for_input, F.text)
async def handle_input_mode_text(message: Message, state: FSMContext) -> None:
    from bot.handlers.chat import run_agent

    data = await state.get_data()
    if time.time() - data.get("created_at", 0) > _INPUT_TIMEOUT_SEC:
        await state.clear()
        await message.answer("⏱ Время ввода истекло. Нажми кнопку снова — я готов записать!")
        return

    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("Напиши что-нибудь — или нажми кнопку меню для отмены.")
        return

    mode = data.get("input_mode", "")
    if mode == "add_food":
        prompt = f"Запиши в дневник питания: {user_text}"
    elif mode == "log_workout":
        prompt = f"Запиши тренировку как выполненную: {user_text}"
    else:
        prompt = user_text

    await state.clear()
    placeholder = await message.answer("_Обрабатываю..._", parse_mode=ParseMode.MARKDOWN)
    response = await run_agent(message, prompt, existing_placeholder=placeholder)

    if mode == "log_workout" and response and "🏆" in response:
        from bot.keyboards.main import cycle_complete_keyboard
        await message.answer(
            "_Выбери что делаем дальше:_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cycle_complete_keyboard(),
        )


@router.message(InputModeFSM.waiting_for_input)
async def handle_input_mode_non_text(message: Message) -> None:
    await message.answer("Напиши текстом — или нажми кнопку меню для отмены.")
