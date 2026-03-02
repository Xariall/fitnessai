"""Пакет хендлеров — экспортирует все роутеры."""

from bot.handlers.common import router as common_router
from bot.handlers.onboarding import router as onboarding_router

__all__ = ["common_router", "onboarding_router"]
