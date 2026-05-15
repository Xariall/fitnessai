from typing import TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: list[BaseMessage]
    user_profile: dict
    telegram_user_id: int
