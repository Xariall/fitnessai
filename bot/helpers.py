"""Shared bot helpers — no LLM, direct DB reads."""
import logging

from db.client import get_client

logger = logging.getLogger(__name__)


async def get_cycle_banner(user_id: str) -> str | None:
    """Return a formatted active-cycle status banner, or None if no active cycle.

    Used in show_workout_history and get_next_session_plan to prepend cycle context.
    Logs a warning (with cycle_id) if the stored schedule JSON is malformed.
    """
    client = await get_client()
    rows = (
        await client.table("training_cycles")
        .select(
            "id,title,current_week,total_weeks,current_session_index,"
            "sessions_per_week,schedule,total_sessions_done"
        )
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not rows:
        return None

    c = rows[0]
    try:
        session = c["schedule"]["weeks"][c["current_week"] - 1]["sessions"][
            c["current_session_index"]
        ]
        total = c["total_weeks"] * c["sessions_per_week"]
        pct = int(c["total_sessions_done"] / total * 100) if total else 0
        return (
            f"📅 *{c['title']}* · Неделя {c['current_week']} из {c['total_weeks']} ({pct}%)\n"
            f"Следующая: {session['label']}\n\n"
        )
    except (IndexError, KeyError, TypeError) as exc:
        logger.warning(
            "get_cycle_banner: failed to parse schedule cycle_id=%s: %s",
            c.get("id"),
            exc,
        )
        return None
