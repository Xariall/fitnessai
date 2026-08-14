import asyncio
import logging

from langchain_core.messages import SystemMessage, ToolMessage

from agent.prompts.system import SYSTEM_PROMPT
from agent.state import AgentState
from llm.provider import get_llm, get_llm_thinking

logger = logging.getLogger(__name__)


async def _invoke_llm_with_retry(llm_with_tools, messages: list, telegram_user_id: int, log_prefix: str):
    """Вызов LLM с ретраем на временную недоступность Gemini (503).

    Общий хелпер для planner и domain_planner — раньше эта логика была
    продублирована бы в каждом из 5 доменных узлов.
    """
    last_exc = None
    for attempt in range(3):
        try:
            return await llm_with_tools.ainvoke(messages)
        except Exception as exc:
            last_exc = exc
            is_retryable = "503" in str(exc) or "unavailable" in str(exc).lower()
            if is_retryable and attempt < 2:
                delay = 3 * (attempt + 1)
                logger.warning(
                    "%s: Gemini 503, retry %d in %ds for user %s",
                    log_prefix, attempt + 1, delay, telegram_user_id,
                )
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exc


def _correct_hallucinated_user_id(response, correct_id: int):
    """Гарантирует правильный telegram_user_id во всех tool calls —
    модель иногда галлюцинирует placeholder-значения (напр. 123456789).
    """
    if not getattr(response, "tool_calls", None):
        return response
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
    return response.model_copy(update={"tool_calls": fixed})


async def load_profile(state: AgentState) -> dict:
    """Узел: подгружает профиль пользователя перед обработкой."""
    from db.client import fetchrow

    telegram_user_id = state["telegram_user_id"]
    try:
        row = await fetchrow(
            "SELECT * FROM users WHERE telegram_user_id = $1",
            telegram_user_id,
        )
        if row is None:
            logger.warning("load_profile: user %s not found or DB error", telegram_user_id)
            return {"user_profile": {}}
        return {"user_profile": row}
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

    response = await _invoke_llm_with_retry(llm_with_tools, messages, state["telegram_user_id"], "planner")
    response = _correct_hallucinated_user_id(response, state["telegram_user_id"])

    return {"messages": [response]}


async def responder(state: AgentState) -> AgentState:
    """Узел: формирует финальный ответ пользователю."""
    # Последнее сообщение уже содержит ответ агента
    return state


async def router_node(state: AgentState) -> dict:
    """Узел: определяет домен текущего хода (workout/nutrition/progress/motivation/general).

    Активен только когда settings.enable_subagent_router=True — см. agent/router.py.
    """
    from agent.router import resolve_domain

    telegram_user_id = state["telegram_user_id"]
    last_message = state["messages"][-1] if state["messages"] else None
    user_text = str(last_message.content) if last_message is not None else ""

    domain = await resolve_domain(telegram_user_id, user_text)
    logger.info("router_node: user %s → domain=%s", telegram_user_id, domain)
    return {"active_domain": domain}


async def domain_planner(state: AgentState) -> AgentState:
    """Узел: planner, параметризованный текущим доменом (state["active_domain"]).

    В отличие от planner (все 35 tools + весь SYSTEM_PROMPT каждый ход), здесь
    LLM видит только инструменты и промпт своего домена — см. agent/router.py
    TOOLS_BY_DOMAIN / DOMAIN_PROMPTS.
    """
    from agent.router import DOMAIN_PROMPTS, TOOLS_BY_DOMAIN

    domain = state["active_domain"]
    tools = TOOLS_BY_DOMAIN[domain]

    has_tool_results = any(isinstance(m, ToolMessage) for m in state["messages"])
    llm = get_llm_thinking() if has_tool_results else get_llm()
    llm_with_tools = llm.bind_tools(tools)

    profile = state["user_profile"]
    injuries: list[str] = profile.get("injuries") or []
    injuries_section = _build_injuries_section(injuries)

    system_content = DOMAIN_PROMPTS[domain].format(
        user_profile=profile,
        telegram_user_id=state["telegram_user_id"],
        injuries_section=injuries_section,
    )
    system_message = SystemMessage(content=system_content)
    messages = [system_message] + state["messages"]

    response = await _invoke_llm_with_retry(
        llm_with_tools, messages, state["telegram_user_id"], f"domain_planner[{domain}]"
    )
    response = _correct_hallucinated_user_id(response, state["telegram_user_id"])

    return {"messages": [response]}
