"""
Локальное тестирование AI агента без Telegram.
- db.client._client заменяется моком → load_profile не обращается к Supabase
- Инструменты (log_food, log_workout и т.д.) тоже используют мок

Запуск: python test_agent_local.py
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

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


def _build_supabase_mock() -> MagicMock:
    """
    Мок для Supabase AsyncClient.
    Поддерживает цепочки: .table(...).select(...).eq(...).single().execute()
    и вставки: .table(...).insert(...).execute()
    """
    profile_result = MagicMock(data=MOCK_PROFILE)
    empty_result = MagicMock(data=[], count=0)

    def make_builder(final_data=None):
        result = MagicMock(data=final_data if final_data is not None else [])
        builder = MagicMock()
        builder.execute = AsyncMock(return_value=result)
        builder.single = MagicMock(return_value=MagicMock(
            execute=AsyncMock(return_value=result)
        ))
        builder.eq = MagicMock(return_value=builder)
        builder.select = MagicMock(return_value=builder)
        builder.insert = MagicMock(return_value=builder)
        builder.update = MagicMock(return_value=builder)
        builder.upsert = MagicMock(return_value=builder)
        builder.order = MagicMock(return_value=builder)
        builder.limit = MagicMock(return_value=builder)
        builder.gte = MagicMock(return_value=builder)
        builder.lte = MagicMock(return_value=builder)
        return builder

    users_builder = make_builder(MOCK_PROFILE)
    # Для single() возвращаем профиль
    users_builder.single = MagicMock(return_value=MagicMock(
        execute=AsyncMock(return_value=MagicMock(data=MOCK_PROFILE))
    ))

    client = MagicMock()

    def table_router(name: str):
        if name == "users":
            return users_builder
        return make_builder([])

    client.table = MagicMock(side_effect=table_router)
    return client


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
    # Инжектируем мок ДО инициализации графа
    import db.client as db_module
    db_module._client = _build_supabase_mock()

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
