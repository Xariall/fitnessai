"""Google OAuth 2.0 + JWT session management for FastAPI."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt

from database.db import get_or_create_user, get_user_by_id
from database.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Config ───────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _get_redirect_uri() -> str:
    """
    Resolve the Google OAuth callback URI at request time.

    Priority:
      1. GOOGLE_REDIRECT_URI  — explicit full URI (recommended for production)
      2. FASTAPI_BASE_URL     — auto-appends /api/auth/callback
      3. Fallback to localhost
    """
    explicit = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    base = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/auth/callback"


def _get_frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# ── JWT helpers ──────────────────────────────────────────────────────────────

def create_jwt(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "exp": expire,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── Auth dependency ──────────────────────────────────────────────────────────

async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias="session_token")] = None,
) -> User:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_jwt(session_token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


OptionalUser = Annotated[User | None, Depends(
    lambda session_token: None
)]


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login() -> RedirectResponse:
    """Initiate Google OAuth flow."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")

    redirect_uri = _get_redirect_uri()
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
async def google_callback(
    code: str = Query(...),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle Google OAuth callback, set JWT cookie, redirect to frontend."""
    frontend_url = _get_frontend_url()
    redirect_uri = _get_redirect_uri()

    if error:
        return RedirectResponse(url=f"{frontend_url}/?error={error}")

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend_url}/?error=token_exchange_failed")

        access_token = token_resp.json().get("access_token")
        if not access_token:
            return RedirectResponse(url=f"{frontend_url}/?error=no_access_token")

        # Fetch user info from Google
        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend_url}/?error=userinfo_failed")

        info = user_resp.json()

    google_id = info.get("sub")
    if not google_id:
        return RedirectResponse(url=f"{frontend_url}/?error=missing_sub")

    user = await get_or_create_user(
        google_id=google_id,
        email=info.get("email"),
        name=info.get("name"),
        picture=info.get("picture"),
    )

    token = create_jwt(user)

    # Pass JWT to frontend via query param; Express will set the httpOnly cookie
    return RedirectResponse(url=f"{frontend_url}/api/oauth/finish?token={token}")


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "google_id": user.google_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "age": user.age,
        "height": user.height,
        "weight": user.weight,
        "gender": user.gender,
        "activity": user.activity,
        "goal": user.goal,
    }


@router.post("/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"success": True})
    response.delete_cookie("session_token")
    return response
