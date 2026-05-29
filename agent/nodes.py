import asyncio
import logging

from langchain_core.messages import SystemMessage, ToolMessage

from agent.prompts.system import SYSTEM_PROMPT
from agent.state import AgentState
from llm.provider import get_llm, get_llm_thinking

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


_INJURY_LABELS: dict[str, str] = {
    "knee_injury": "колено",
    "lower_back": "поясница",
    "shoulder_injury": "плечо",
    "elbow": "локоть",
    "wrist": "запястье",
    "hip": "бедро/таз",
    "neck": "шея",
}


def _build_injuries_section(injuries: list[str]) -> str:
    if not injuries:
        return ""
    listed = ", ".join(_INJURY_LABELS.get(i, i) for i in injuries)
    return (
        f"## ⚠️ ПРОТИВОПОКАЗАНИЯ ПОЛЬЗОВАТЕЛЯ\n"
        f"Травмы: **{listed}**\n"
        f"generate_workout_plan автоматически исключает опасные упражнения.\n"
        f"НИКОГДА не предлагай упражнения с нагрузкой на эти зоны вручную."
    )


async def planner(state: AgentState, tools: list) -> AgentState:
    """Узел: планировщик — вызывает LLM с системным промптом и инструментами."""
    from agent.chat_modes import get_mode

    # С thinking только когда уже есть результаты инструментов — синтез требует рассуждений.
    # Для первичного планирования и базовых запросов thinking отключён — быстрее.
    has_tool_results = any(isinstance(m, ToolMessage) for m in state["messages"])
    llm = get_llm_thinking() if has_tool_results else get_llm()
    llm_with_tools = llm.bind_tools(tools)

    profile = state["user_profile"]
    injuries: list[str] = profile.get("injuries") or []
    injuries_section = _build_injuries_section(injuries)

    base_content = SYSTEM_PROMPT.format(
        user_profile=profile,
        telegram_user_id=state["telegram_user_id"],
        injuries_section=injuries_section,
    )
    mode = get_mode(state["telegram_user_id"])
    system_content = base_content + ("\n\n" + mode.prompt_suffix if mode.prompt_suffix else "")

    system_message = SystemMessage(content=system_content)
    messages = [system_message] + state["messages"]

    last_exc = None
    for attempt in range(3):
        try:
            response = await llm_with_tools.ainvoke(messages)
            break
        except Exception as exc:
            last_exc = exc
            is_retryable = "503" in str(exc) or "unavailable" in str(exc).lower()
            if is_retryable and attempt < 2:
                delay = 3 * (attempt + 1)
                logger.warning(
                    "planner: Gemini 503, retry %d in %ds for user %s",
                    attempt + 1, delay, state["telegram_user_id"],
                )
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise last_exc

    # Гарантируем правильный telegram_user_id во всех tool calls —
    # модель иногда галлюцинирует placeholder-значения (напр. 123456789).
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
