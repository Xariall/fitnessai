import logging
import os
import pickle
from functools import partial
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes import domain_planner, load_profile, planner, responder, router_node
from agent.state import AgentState
from config import settings
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
    generate_cycle_preview,
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
    replace_workout_exercise,
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
    generate_cycle_preview,
    create_training_cycle,
    get_active_cycle,
    get_next_session_plan,
    get_cycle_summary,
    get_cycle_by_id,
    replace_workout_exercise,
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


def _build_flat_graph(graph: StateGraph) -> None:
    """Старый путь: один planner видит все 35 tools + весь SYSTEM_PROMPT каждый ход."""
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


def _build_routed_graph(graph: StateGraph) -> None:
    """Новый путь (settings.enable_subagent_router=True): router выбирает домен,
    domain_planner видит только tools и промпт этого домена.

    tool_executor держит полный набор TOOLS — это исполнитель, а не источник
    схем для LLM, ему не нужна доменная фильтрация (её делает bind_tools внутри
    domain_planner). Известное ограничение: домен фиксируется один раз в начале
    хода, поэтому запрос, требующий tools из двух доменов сразу в одном
    сообщении, новый путь пока не решает так же хорошо как старый плоский —
    проверить на реальных диалогах перед включением в проде (UC-X02 "итог дня").
    """
    graph.add_node("router", router_node)
    graph.add_node("domain_planner", domain_planner)
    graph.add_node("tool_executor", ToolNode(TOOLS))
    graph.add_node("responder", responder)

    graph.set_entry_point("load_profile")
    graph.add_edge("load_profile", "router")
    graph.add_edge("router", "domain_planner")
    graph.add_conditional_edges(
        "domain_planner",
        _should_continue,
        {"tool_executor": "tool_executor", "responder": "responder"},
    )
    graph.add_edge("tool_executor", "domain_planner")
    graph.add_edge("responder", END)


def build_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = MemorySaver()

    graph = StateGraph(AgentState)
    graph.add_node("load_profile", load_profile)

    if settings.enable_subagent_router:
        _build_routed_graph(graph)
    else:
        _build_flat_graph(graph)

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
