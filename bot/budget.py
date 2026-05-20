"""Лимиты запросов к агенту на день (in-memory, сбрасывается при рестарте)."""
from datetime import date


# (user_id, date_str) -> количество запросов за день
_daily_counts: dict[tuple[int, str], int] = {}


def _today() -> str:
    return date.today().isoformat()


def is_allowed(user_id: int, max_per_day: int) -> bool:
    """True если пользователь не исчерпал дневной лимит. 0 = безлимитно."""
    if max_per_day <= 0:
        return True
    return _daily_counts.get((user_id, _today()), 0) < max_per_day


def increment(user_id: int) -> int:
    """Увеличивает счётчик и возвращает новое значение."""
    key = (user_id, _today())
    _daily_counts[key] = _daily_counts.get(key, 0) + 1
    return _daily_counts[key]


def get_count(user_id: int) -> int:
    return _daily_counts.get((user_id, _today()), 0)


def get_remaining(user_id: int, max_per_day: int) -> int:
    """Возвращает оставшееся число запросов. -1 если безлимитно."""
    if max_per_day <= 0:
        return -1
    return max(0, max_per_day - get_count(user_id))
