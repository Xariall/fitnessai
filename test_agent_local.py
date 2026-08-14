"""
Локальное тестирование AI агента без Telegram.
- db.client.fetch/fetchrow/execute заменяются моками → load_profile не обращается к Postgres
- Инструменты (log_food, log_workout и т.д.) тоже используют моки (no-op write, read → users отдаёт профиль, остальное — пусто)

Запуск: python test_agent_local.py
"""
import asyncio
import logging
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for noisy in ("httpx", "httpcore", "hpack"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

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
}


async def _mock_fetchrow(query: str, *args):
    if "FROM users" in query:
        return dict(MOCK_PROFILE)
    return None


async def _mock_fetch(query: str, *args) -> list[dict]:
    return []


async def _mock_execute(query: str, *args) -> str:
    return "OK"


async def run_agent(message: str, thread_id: str) -> str:
    import agent.graph as gm
    config = {"configurable": {"thread_id": thread_id}}
    state = {
        "messages": [HumanMessage(content=message)],
        "user_profile": {},
        "telegram_user_id": MOCK_USER_ID,
    }
    result = await gm.agent_graph.ainvoke(state, config=config)
    return result["messages"][-1].content


async def main():
    # Инжектируем моки ДО инициализации графа — все модули делают
    # `from db.client import fetch, fetchrow, execute` при импорте, поэтому
    # патчим db.client раньше любого `import agent.graph`.
    import db.client as db_module
    db_module.fetch = AsyncMock(side_effect=_mock_fetch)
    db_module.fetchrow = AsyncMock(side_effect=_mock_fetchrow)
    db_module.execute = AsyncMock(side_effect=_mock_execute)

    from agent.graph import init_graph
    await init_graph()

    print("=" * 60)
    print("  FitnessAI — Локальный тест агента (без Telegram)")
    print(f"  Профиль: {MOCK_PROFILE['name']}, {MOCK_PROFILE['age']}л, "
          f"{MOCK_PROFILE['weight_kg']}кг, цель: {MOCK_PROFILE['goal']}")
    print("  Введите 'выход' для завершения")
    print("=" * 60)
    print()

    thread_id = "local-test-001"

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nЗавершение.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("выход", "exit", "quit"):
            print("Завершение.")
            break

        print("⏳ Думает...", flush=True)
        try:
            response = await run_agent(user_input, thread_id)
            print(f"\nАгент: {response}\n")
        except Exception as e:
            logging.exception("Ошибка агента")
            print(f"[Ошибка]: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
