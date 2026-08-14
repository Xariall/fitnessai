from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # add_messages — reducer, который добавляет новые сообщения к существующим,
    # а не заменяет весь список. Необходим для корректной работы checkpointer.
    messages: Annotated[list[BaseMessage], add_messages]
    user_profile: dict
    telegram_user_id: int
    # Домен текущего хода (workout/nutrition/progress/motivation/general).
    # Пересчитывается роутером на каждом ходу — см. agent/router.py.
    # Используется только когда settings.enable_subagent_router=True.
    active_domain: str
