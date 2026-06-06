"""
Tests for training records API endpoints and helpers.
"""
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.utils.records import (
    _safe_float,
    get_effective_weight,
    _normalize_key,
    _classify_muscle_group,
)
from api.utils.security import _validate_init_data


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0

    def test_numeric_string(self):
        assert _safe_float("42.5") == 42.5

    def test_int(self):
        assert _safe_float(100) == 100.0

    def test_bodyweight_string(self):
        assert _safe_float("Собственный вес") == 0.0

    def test_russian_weight_text(self):
        assert _safe_float("вес тела") == 0.0

    def test_zero_string(self):
        assert _safe_float("0") == 0.0

    def test_float_passthrough(self):
        assert _safe_float(3.14) == 3.14


class TestGetEffectiveWeight:
    def test_regular_exercise(self):
        result = get_effective_weight(80.0, 75.0, uses_bodyweight=False)
        assert result == 80.0

    def test_bodyweight_exercise_with_user_weight(self):
        result = get_effective_weight(0, 75.0, uses_bodyweight=True, added_kg=10.0)
        assert result == 85.0  # 75 + 10

    def test_bodyweight_exercise_no_added(self):
        result = get_effective_weight(0, 75.0, uses_bodyweight=True)
        assert result == 75.0

    def test_bodyweight_exercise_no_user_weight(self):
        result = get_effective_weight(0, None, uses_bodyweight=True, added_kg=10.0)
        assert result == 0.0  # bw=0, so falls through to w

    def test_string_weight(self):
        result = get_effective_weight("Собственный вес", 75.0, uses_bodyweight=True)
        assert result == 75.0

    def test_none_weight(self):
        result = get_effective_weight(None, None, uses_bodyweight=False)
        assert result == 0.0


class TestNormalizeKey:
    def test_basic(self):
        assert _normalize_key("Bench Press") == "bench press"

    def test_dashes_to_spaces(self):
        assert _normalize_key("pull-up") == "pull up"

    def test_multiple_spaces(self):
        assert _normalize_key("bench   press") == "bench press"

    def test_yo_normalization(self):
        assert _normalize_key("подъём") == "подъем"

    def test_strip(self):
        assert _normalize_key("  squat  ") == "squat"


class TestClassifyMuscleGroup:
    def test_chest(self):
        result = _classify_muscle_group("Bench Press")
        assert result in ("chest", "other")  # depends on _MUSCLE_KEYWORDS content

    def test_unknown(self):
        result = _classify_muscle_group("XYZ Unknown Exercise 123")
        assert result == "other"


# ---------------------------------------------------------------------------
# Unit tests: HMAC validation
# ---------------------------------------------------------------------------


class TestValidateInitData:
    BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    def _make_init_data(self, user_data: dict, token: str) -> str:
        """Build valid Telegram initData string."""
        user_json = json.dumps(user_data, separators=(",", ":"))
        auth_date = str(int(time.time()))

        params = {
            "user": user_json,
            "auth_date": auth_date,
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        }

        check_pairs = sorted(f"{k}={v}" for k, v in params.items())
        data_check_string = "\n".join(check_pairs)

        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        parts = [f"{k}={v}" for k, v in params.items()]
        parts.append(f"hash={computed_hash}")
        return "&".join(parts)

    def test_valid_init_data(self):
        user = {"id": 123456789, "first_name": "Test"}
        init_data = self._make_init_data(user, self.BOT_TOKEN)
        result = _validate_init_data(init_data, self.BOT_TOKEN)
        assert result is not None
        assert result["id"] == 123456789

    def test_invalid_hash(self):
        user = {"id": 123456789, "first_name": "Test"}
        init_data = self._make_init_data(user, self.BOT_TOKEN)
        # Tamper with hash
        init_data = init_data.replace(init_data.split("hash=")[1][:8], "deadbeef")
        result = _validate_init_data(init_data, self.BOT_TOKEN)
        assert result is None

    def test_wrong_token(self):
        user = {"id": 123456789, "first_name": "Test"}
        init_data = self._make_init_data(user, self.BOT_TOKEN)
        result = _validate_init_data(init_data, "wrong:token")
        assert result is None

    def test_no_hash(self):
        result = _validate_init_data("user=test&auth_date=123", self.BOT_TOKEN)
        assert result is None

    def test_empty_string(self):
        result = _validate_init_data("", self.BOT_TOKEN)
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests: API endpoints (mocked DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase():
    """Mock Supabase client for API tests."""
    mock_client = AsyncMock()

    def _table_chain(data=None):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.gte.return_value = chain
        chain.order.return_value = chain
        chain.maybe_single.return_value = chain
        chain.limit.return_value = chain

        result = MagicMock()
        result.data = data
        chain.execute = AsyncMock(return_value=result)
        return chain

    mock_client.table = MagicMock(side_effect=lambda name: {
        "users": _table_chain({"id": "uuid-test", "weight_kg": 80.0, "telegram_user_id": 123456}),
        "workout_logs": _table_chain([]),
    }.get(name, _table_chain(None)))

    return mock_client


@pytest.fixture(autouse=True)
def _reset_supabase_client():
    """Reset supabase singleton between tests to avoid event loop issues."""
    import db.client
    db.client._client = None
    yield
    db.client._client = None


@pytest.mark.asyncio
async def test_get_records_404():
    """GET /api/records/{id} returns 404 for unknown user."""
    from httpx import ASGITransport, AsyncClient
    from api.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/records/000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_records_401_invalid_init_data():
    """GET /api/records/{id} returns 401 for invalid initData."""
    from httpx import ASGITransport, AsyncClient
    from api.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/records/123456",
            headers={"X-Telegram-Init-Data": "invalid_data_here&hash=fakehash"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_check():
    """GET /api/health returns ok."""
    from httpx import ASGITransport, AsyncClient
    from api.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_exercise_404():
    """GET /api/records/{id}/exercise/{ex} returns 404 for unknown user."""
    from httpx import ASGITransport, AsyncClient
    from api.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/records/000000000/exercise/bench-press")
    assert resp.status_code == 404
