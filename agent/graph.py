import logging
from functools import partial

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes import load_profile, planner, responder
from agent.state import AgentState
from agent.tools.motivation import send_motivation
from agent.tools.nutrition import (
    calculate_daily_calories,
    generate_nutrition_plan,
    get_daily_nutrition_summary,
    get_food_info,
    log_food,
)
from agent.tools.profile import get_user_profile, update_user_profile
from agent.tools.progress import get_progress_summary, log_progress
from agent.tools.workouts import (
    find_exercises,
    generate_workout_plan,
    get_workout_history,
    log_workout,
)

logger = logging.getLogger(__name__)

TOOLS = [
    get_user_profile,
    update_user_profile,
    generate_workout_plan,
    log_workout,
    get_workout_history,
    find_exercises,
    calculate_daily_calories,
    generate_nutrition_plan,
    log_food,
    get_daily_nutrition_summary,
    get_food_info,
    log_progress,
    get_progress_summary,
    send_motivation,
]


def _should_continue(state: AgentState) -> str:
    """Переход после planner:
    - есть tool_calls → tool_executor (выполнить инструменты, вернуться в planner)
    - нет tool_calls  → responder (сформировать финальный ответ)
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_executor"
    return "responder"


def build_graph() -> StateGraph:
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

    return graph.compile()


agent_graph = build_graph()
