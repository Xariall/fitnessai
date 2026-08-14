"""Shadow-test: сравнение старого плоского graph'а и нового routed graph'а
(settings.enable_subagent_router) на одних и тех же сценариях без Telegram.

Зачем: перед тем как включать ENABLE_SUBAGENT_ROUTER в проде, нужно убедиться,
что домен определяется верно и что урезанный набор tools не ломает сценарии,
которые раньше решались одним planner'ом со всеми 35 tools сразу.

Требует настоящего LLM (GEMINI_API_KEY в .env, или локальный Ollama — смотри
llm/provider.py). Supabase замокан — реальная БД не нужна и не трогается.

Запуск:
    python scripts/shadow_test_router.py
    python scripts/shadow_test_router.py --domain nutrition   # только один домен
"""
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Добавить корневую директорию проекта в путь — так же, как в scripts/generate_ru_names.py
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

MOCK_USER_ID = 99999
MOCK_PROFILE = {
    "id": "00000000-0000-0000-0000-000000099999",
    "telegram_user_id": MOCK_USER_ID,
    "name": "Тест",
    "age": 28,
    "weight_kg": 80.0,
    "height_cm": 180.0,
    "goal": "lose_weight",
    "activity_level": "moderate",
    "injuries": [],
}

# Сценарии из docs/use_cases.md — по одному на домен + помеченный кросс-доменный
# кейс (UC-X02 "вечерний итог дня"), который известное ограничение нового пути
# (домен фиксируется один раз в начале хода, см. agent/graph.py::_build_routed_graph).
SCENARIOS: list[tuple[str, str, str]] = [
    ("workout", "составь тренировку на ноги", "UC-T01"),
    ("nutrition", "съел гречку 200г", "UC-N03"),
    ("progress", "вешу 87кг", "замер веса"),
    ("motivation", "не хочу тренироваться", "мотивация"),
    ("general", "мне теперь 31 год", "обновление профиля"),
    ("cross-domain?", "как прошёл день?", "UC-X02 — известный edge case, см. docstring"),
]


def _build_supabase_mock() -> MagicMock:
    """Тот же паттерн мока, что в test_agent_local.py — .table(...).select()...execute()."""

    def make_builder(final_data=None):
        result = MagicMock(data=final_data if final_data is not None else [])
        builder = MagicMock()
        builder.execute = AsyncMock(return_value=result)
        builder.single = MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=result)))
        for method in ("eq", "select", "insert", "update", "upsert", "order", "limit", "gte", "lte"):
            setattr(builder, method, MagicMock(return_value=builder))
        return builder

    users_builder = make_builder(MOCK_PROFILE)
    users_builder.single = MagicMock(
        return_value=MagicMock(execute=AsyncMock(return_value=MagicMock(data=MOCK_PROFILE)))
    )

    client = MagicMock()
    client.table = MagicMock(
        side_effect=lambda name: users_builder if name == "users" else make_builder([])
    )
    return client


def _extract_tool_calls(messages: list) -> list[str]:
    names: list[str] = []
    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            names.extend(tc["name"] for tc in m.tool_calls)
    return names


async def _run_once(message: str, enable_router: bool, thread_id: str) -> dict:
    import agent.graph as graph_module

    with patch.object(graph_module.settings, "enable_subagent_router", enable_router):
        graph = graph_module.build_graph()
        state = {
            "messages": [HumanMessage(content=message)],
            "user_profile": {},
            "telegram_user_id": MOCK_USER_ID,
        }
        config = {"configurable": {"thread_id": thread_id}}
        started = time.monotonic()
        try:
            result = await graph.ainvoke(state, config=config)
            elapsed = time.monotonic() - started
            return {
                "ok": True,
                "response": result["messages"][-1].content,
                "tool_calls": _extract_tool_calls(result["messages"]),
                "active_domain": result.get("active_domain"),
                "elapsed_s": round(elapsed, 2),
            }
        except Exception as exc:
            elapsed = time.monotonic() - started
            return {"ok": False, "error": repr(exc), "elapsed_s": round(elapsed, 2)}


async def run_scenario(expected_domain: str, message: str, note: str, index: int) -> None:
    print("=" * 78)
    print(f"[{index}] {note}")
    print(f"Сообщение: {message!r}   (ожидаемый домен: {expected_domain})")
    print("-" * 78)

    flat = await _run_once(message, enable_router=False, thread_id=f"shadow-flat-{index}")
    routed = await _run_once(message, enable_router=True, thread_id=f"shadow-routed-{index}")

    print("СТАРЫЙ (flat planner, все 35 tools):")
    if flat["ok"]:
        print(f"  tool_calls: {flat['tool_calls']}")
        print(f"  время: {flat['elapsed_s']}s")
        print(f"  ответ: {flat['response'][:300]}")
    else:
        print(f"  ОШИБКА: {flat['error']}")

    print()
    print("НОВЫЙ (routed, только tools своего домена):")
    if routed["ok"]:
        print(f"  выбранный домен: {routed['active_domain']}")
        print(f"  tool_calls: {routed['tool_calls']}")
        print(f"  время: {routed['elapsed_s']}s")
        print(f"  ответ: {routed['response'][:300]}")
    else:
        print(f"  ОШИБКА: {routed['error']}")
    print()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", help="прогнать только сценарии этого домена (workout/nutrition/...)")
    args = parser.parse_args()

    import db.client as db_module
    db_module._client = _build_supabase_mock()

    scenarios = SCENARIOS
    if args.domain:
        scenarios = [s for s in SCENARIOS if s[0] == args.domain]
        if not scenarios:
            print(f"Нет сценариев для домена '{args.domain}'. Доступные: {[s[0] for s in SCENARIOS]}")
            return

    print(f"Прогоняю {len(scenarios)} сценариев через оба пути графа (flat vs routed)...")
    print()
    for i, (domain, message, note) in enumerate(scenarios, 1):
        await run_scenario(domain, message, note, i)


if __name__ == "__main__":
    asyncio.run(main())
