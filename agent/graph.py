import logging
import os
import pickle
from functools import partial
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes import load_profile, planner, responder
from agent.state import AgentState
from agent.tools.motivation import generate_motivation_meme, send_motivation
from agent.tools.nutrition import (
    calculate_daily_calories,
    calculate_hydration,
    check_nutrition_adjustment,
    delete_log_entry,
    generate_nutrition_plan,
    get_daily_nutrition_summary,
    get_food_info,
    get_workout_nutrition_protocol,
    log_food,
)
from agent.tools.profile import get_user_profile, update_user_profile
from agent.tools.progress import get_progress_summary, get_weekly_summary, log_progress
from agent.tools.workouts import (
    adjust_cycle_schedule,
    check_recovery_status,
    create_training_cycle,
    find_exercises,
    generate_weekly_debrief,
    generate_workout_plan,
    get_active_cycle,
    get_cycle_by_id,
    get_cycle_summary,
    get_exercise_history,
    get_next_session_plan,
    get_recovery_overview,
    get_training_roadmap,
    get_weekly_volume,
    get_workout_history,
    log_workout,
    update_user_injuries,
)

logger = logging.getLogger(__name__)

TOOLS = [
    get_user_profile,
    update_user_profile,
    # workouts
    generate_workout_plan,
    log_workout,
    get_workout_history,
    get_exercise_history,
    get_training_roadmap,
    get_weekly_volume,
    find_exercises,
    check_recovery_status,
    get_recovery_overview,
    create_training_cycle,
    get_active_cycle,
    get_next_session_plan,
    get_cycle_summary,
    get_cycle_by_id,
    update_user_injuries,
    adjust_cycle_schedule,
    generate_weekly_debrief,
    # nutrition
    calculate_daily_calories,
    generate_nutrition_plan,
    log_food,
    delete_log_entry,
    get_daily_nutrition_summary,
    get_food_info,
    get_workout_nutrition_protocol,
    check_nutrition_adjustment,
    calculate_hydration,
    # progress
    log_progress,
    get_progress_summary,
    get_weekly_summary,
    # motivation
    send_motivation,
    generate_motivation_meme,
]

_CHECKPOINT_FILE = Path(__file__).parent.parent / "data" / "checkpoints.pkl"

# Инициализируется при вызове init_graph() в bot/main.py
agent_graph = None
_checkpointer: MemorySaver | None = None


def _should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_executor"
    return "responder"


def build_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = MemorySaver()

    graph = StateGraph(AgentState)
    graph.add_node("load_profile", load_profile)
    graph.add_node("planner", partial(planner, tools=TOOLS))
    graph.add_node("tool_executor", ToolNode(TOOLS))
    graph.add_node("responder", responder)

    graph.set_entry_point("load_profile")
    graph.add_edge("load_profile", "planner")
    graph.add_conditional_edges(
        "planner",
        _should_continue,
        {"tool_executor": "tool_executor", "responder": "responder"},
    )
    graph.add_edge("tool_executor", "planner")
    graph.add_edge("responder", END)

    return graph.compile(checkpointer=checkpointer)


async def init_graph() -> None:
    """Инициализирует граф агента.

    Загружает сохранённые checkpoints из файла (если есть),
    чтобы пользователи не теряли историю диалога при рестарте бота.
    """
    global agent_graph, _checkpointer

    _checkpointer = MemorySaver()

    if _CHECKPOINT_FILE.exists():
        try:
            with open(_CHECKPOINT_FILE, "rb") as f:
                saved = pickle.load(f)
            _checkpointer.storage.update(saved)
            logger.info(
                "Persistent memory: loaded %d conversation threads from %s",
                len(saved),
                _CHECKPOINT_FILE,
            )
        except Exception:
            logger.warning(
                "Could not load checkpoints from %s, starting fresh",
                _CHECKPOINT_FILE,
                exc_info=True,
            )
    else:
        logger.info("Persistent memory: no checkpoint file found, starting fresh")

    agent_graph = build_graph(_checkpointer)


async def cleanup_graph() -> None:
    """Сохраняет checkpoints на диск при остановке бота."""
    global _checkpointer
    if _checkpointer is None:
        return
    try:
        _CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CHECKPOINT_FILE, "wb") as f:
            pickle.dump(dict(_checkpointer.storage), f)
        logger.info(
            "Persistent memory: saved %d conversation threads to %s",
            len(_checkpointer.storage),
            _CHECKPOINT_FILE,
        )
    except Exception:
        logger.exception("Failed to save checkpoints to %s", _CHECKPOINT_FILE)


def clear_thread(telegram_user_id: int) -> None:
    """Удаляет историю диалога пользователя из памяти агента."""
    if _checkpointer is None:
        return
    thread_id = str(telegram_user_id)
    _checkpointer.storage.pop(thread_id, None)
