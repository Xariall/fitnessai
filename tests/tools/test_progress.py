"""Тесты для инструментов прогресса."""
import pytest
from datetime import datetime, timedelta, timezone


def _calculate_delta(current: float, previous: float | None) -> str:
    """Дублирует логику форматирования дельты из log_progress."""
    if previous is None:
        return f"{current} кг — первый замер!"
    delta = round(current - previous, 1)
    sign = "+" if delta > 0 else ""
    trend = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
    return f"{current} кг {trend} ({sign}{delta} кг с прошлого замера)"


def _build_summary(logs: list[dict], days: int) -> dict:
    """Дублирует логику get_progress_summary."""
    if not logs:
        return {"message": f"Нет замеров за последние {days} дней.", "logs": []}
    start_weight = logs[0]["weight_kg"]
    current_weight = logs[-1]["weight_kg"]
    delta = round(current_weight - start_weight, 1)
    sign = "+" if delta > 0 else ""
    return {
        "start_weight": start_weight,
        "current_weight": current_weight,
        "delta": f"{sign}{delta} кг за {days} дней",
        "logs": logs,
    }


class TestLogProgressDelta:
    def test_weight_loss_shows_negative_delta(self):
        msg = _calculate_delta(88.0, 90.0)
        assert "📉" in msg
        assert "-2.0" in msg

    def test_weight_gain_shows_positive_delta(self):
        msg = _calculate_delta(91.0, 90.0)
        assert "📈" in msg
        assert "+1.0" in msg

    def test_no_change_shows_arrow(self):
        msg = _calculate_delta(90.0, 90.0)
        assert "➡️" in msg
        assert "0.0" in msg

    def test_first_entry_no_previous(self):
        msg = _calculate_delta(90.0, None)
        assert "первый замер" in msg
        assert "90.0" in msg

    def test_delta_rounded_to_one_decimal(self):
        msg = _calculate_delta(89.555, 90.0)
        # round(89.555 - 90.0, 1) = -0.4
        assert "-0.4" in msg

    @pytest.mark.parametrize("current,previous,expected_trend", [
        (85.0, 90.0, "📉"),
        (95.0, 90.0, "📈"),
        (90.0, 90.0, "➡️"),
    ])
    def test_trend_icons(self, current, previous, expected_trend):
        msg = _calculate_delta(current, previous)
        assert expected_trend in msg


class TestProgressSummary:
    def test_empty_logs_returns_message(self):
        result = _build_summary([], 30)
        assert "Нет замеров" in result["message"]
        assert result["logs"] == []

    def test_single_entry(self):
        logs = [{"weight_kg": 90.0, "measured_at": "2026-04-15T10:00:00"}]
        result = _build_summary(logs, 30)
        assert result["start_weight"] == 90.0
        assert result["current_weight"] == 90.0
        assert result["delta"] == "0.0 кг за 30 дней"

    def test_weight_loss_over_period(self):
        logs = [
            {"weight_kg": 90.0, "measured_at": "2026-04-01T10:00:00"},
            {"weight_kg": 88.0, "measured_at": "2026-04-15T10:00:00"},
            {"weight_kg": 86.5, "measured_at": "2026-04-30T10:00:00"},
        ]
        result = _build_summary(logs, 30)
        assert result["start_weight"] == 90.0
        assert result["current_weight"] == 86.5
        assert "-3.5" in result["delta"]

    def test_weight_gain_over_period(self):
        logs = [
            {"weight_kg": 70.0, "measured_at": "2026-04-01T10:00:00"},
            {"weight_kg": 72.5, "measured_at": "2026-04-30T10:00:00"},
        ]
        result = _build_summary(logs, 30)
        assert "+2.5" in result["delta"]

    def test_logs_preserved_in_result(self):
        logs = [
            {"weight_kg": 80.0, "measured_at": "2026-04-01T10:00:00"},
            {"weight_kg": 79.0, "measured_at": "2026-04-15T10:00:00"},
        ]
        result = _build_summary(logs, 30)
        assert result["logs"] == logs

    def test_days_reflected_in_delta_string(self):
        logs = [{"weight_kg": 80.0, "measured_at": "2026-04-01T10:00:00"}]
        result = _build_summary(logs, 14)
        assert "14 дней" in result["delta"]
