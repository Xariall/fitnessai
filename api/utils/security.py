"""
Telegram initData HMAC-SHA256 validation for API security.
Verifies that requests come from legitimate Telegram Web App sessions.
"""
import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs

from fastapi import Header, HTTPException

from config import settings

logger = logging.getLogger(__name__)


def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validate Telegram initData using HMAC-SHA256.
    Returns parsed data dict if valid, None otherwise.

    Algorithm:
    1. Parse init_data as URL query string
    2. Extract `hash` parameter
    3. Build data-check-string from remaining params (sorted, key=value, \\n separated)
    4. Compute HMAC-SHA256(secret_key, data_check_string)
       where secret_key = HMAC-SHA256("WebAppData", bot_token)
    5. Compare with received hash
    """
    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.pop("hash", [None])[0]

    if not received_hash:
        return None

    # Build data-check-string: sorted key=value pairs joined by \n
    # parse_qs returns lists, take first value for each key
    check_pairs = sorted(
        f"{k}={v[0]}" for k, v in parsed.items()
    )
    data_check_string = "\n".join(check_pairs)

    # Secret key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    # Computed hash
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    # Extract user data
    user_raw = parsed.get("user", [None])[0]
    if user_raw:
        try:
            return json.loads(user_raw)
        except (json.JSONDecodeError, TypeError):
            return None

    return {}


async def verify_telegram_user(
    x_telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
) -> int | None:
    """
    FastAPI dependency: validate Telegram initData and return user ID.
    Returns None if no initData provided (allows unauthenticated dev access).
    Raises 401 if initData is present but invalid.
    """
    if not x_telegram_init_data:
        # No auth header — allow for development
        return None

    user_data = _validate_init_data(x_telegram_init_data, settings.telegram_bot_token)
    if user_data is None:
        logger.warning("Invalid Telegram initData received")
        raise HTTPException(status_code=401, detail="Invalid Telegram authentication")

    user_id = user_data.get("id")
    if not user_id:
        logger.warning("initData valid but no user.id found")
        raise HTTPException(status_code=401, detail="No user ID in authentication data")

    return int(user_id)
