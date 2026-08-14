"""Инструменты агента для тренировок.

Раньше это был один файл agent/tools/workouts.py (2844 строк). Разбит на пакет
по подсекциям (generation/session_log/recovery/cycles/sessions/analysis/debrief),
общие приватные хелперы — в _shared.py.

Реэкспортирует полный публичный API старого модуля, чтобы
`from agent.tools.workouts import X` продолжал работать без изменений
(используется в agent/graph.py и api/utils/records.py).
"""

from ._shared import _calc_1rm, _MUSCLE_KEYWORDS
from .analysis import (
    get_current_max_lifts,
    get_exercise_history,
    get_training_roadmap,
    get_weekly_volume,
)
from .cycles import (
    adjust_cycle_schedule,
    create_training_cycle,
    generate_cycle_preview,
    get_active_cycle,
    get_cycle_by_id,
    get_cycle_summary,
)
from .debrief import generate_weekly_debrief
from .generation import find_exercises, generate_workout_plan
from .recovery import check_recovery_status, get_recovery_overview, update_user_injuries
from .session_log import get_workout_history, log_workout
from .sessions import get_next_session_plan, replace_workout_exercise

__all__ = [
    "_calc_1rm",
    "_MUSCLE_KEYWORDS",
    "adjust_cycle_schedule",
    "check_recovery_status",
    "create_training_cycle",
    "find_exercises",
    "generate_cycle_preview",
    "generate_weekly_debrief",
    "generate_workout_plan",
    "get_active_cycle",
    "get_current_max_lifts",
    "get_cycle_by_id",
    "get_cycle_summary",
    "get_exercise_history",
    "get_next_session_plan",
    "get_recovery_overview",
    "get_training_roadmap",
    "get_weekly_volume",
    "get_workout_history",
    "log_workout",
    "replace_workout_exercise",
    "update_user_injuries",
]
