import logging

from langchain_core.messages import SystemMessage

from agent.prompts.system import SYSTEM_PROMPT
from agent.state import AgentState
from llm.provider import get_llm

logger = logging.getLogger(__name__)


async def load_profile(state: AgentState) -> AgentState:
    """Узел: подгружает профиль пользователя перед обработкой."""
    from db.client import get_client

    telegram_user_id = state["telegram_user_id"]
    client = await get_client()
    result = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .single()
        .execute()
    )
    return {**state, "user_profile": result.data or {}}


async def planner(state: AgentState, tools: list) -> AgentState:
    """Узел: планировщик — вызывает LLM с системным промптом и инструментами."""
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    system_message = SystemMessage(
        content=SYSTEM_PROMPT.format(
            user_profile=state["user_profile"],
            telegram_user_id=state["telegram_user_id"],
        )
    )
    messages = [system_message] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)

    return {**state, "messages": state["messages"] + [response]}


async def responder(state: AgentState) -> AgentState:
    """Узел: формирует финальный ответ пользователю."""
    # Последнее сообщение уже содержит ответ агента
    return state
