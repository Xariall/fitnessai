import logging

from langchain_core.messages import SystemMessage

from agent.prompts.system import SYSTEM_PROMPT
from agent.state import AgentState
from llm.provider import get_llm

logger = logging.getLogger(__name__)


async def load_profile(state: AgentState) -> dict:
    """Узел: подгружает профиль пользователя перед обработкой."""
    from db.client import get_client

    telegram_user_id = state["telegram_user_id"]
    try:
        client = await get_client()
        result = (
            await client.table("users")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .single()
            .execute()
        )
        return {"user_profile": result.data or {}}
    except Exception:
        logger.warning("load_profile: user %s not found or DB error", telegram_user_id)
        return {"user_profile": {}}


async def planner(state: AgentState, tools: list) -> AgentState:
    """Узел: планировщик — вызывает LLM с системным промптом и инструментами."""
    from agent.chat_modes import get_mode

    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    base_content = SYSTEM_PROMPT.format(
        user_profile=state["user_profile"],
        telegram_user_id=state["telegram_user_id"],
    )
    mode = get_mode(state["telegram_user_id"])
    system_content = base_content + ("\n\n" + mode.prompt_suffix if mode.prompt_suffix else "")

    system_message = SystemMessage(content=system_content)
    messages = [system_message] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)

    # Гарантируем правильный telegram_user_id во всех tool calls.
    # qwen2.5 иногда галлюцинирует placeholder-значения (напр. 123456789)
    # вместо реального ID из системного промпта.
    correct_id = state["telegram_user_id"]
    if getattr(response, "tool_calls", None):
        fixed = []
        for tc in response.tool_calls:
            args = tc.get("args", {})
            if "telegram_user_id" in args and args["telegram_user_id"] != correct_id:
                logger.warning(
                    "Correcting hallucinated telegram_user_id in tool call %s: %s → %s",
                    tc.get("name"),
                    args["telegram_user_id"],
                    correct_id,
                )
                args = {**args, "telegram_user_id": correct_id}
                tc = {**tc, "args": args}
            fixed.append(tc)
        response = response.model_copy(update={"tool_calls": fixed})

    return {"messages": [response]}


async def responder(state: AgentState) -> AgentState:
    """Узел: формирует финальный ответ пользователю."""
    # Последнее сообщение уже содержит ответ агента
    return state
