"""Single user password auth with signed cookies, plus the read-only kiosk cookie."""

from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .settings import Settings, get_settings

log = logging.getLogger("frankenstein.auth")

SESSION_COOKIE = "fc_session"
KIOSK_COOKIE = "fc_kiosk"

_attempts: dict[str, deque[float]] = defaultdict(deque)
RATE_LIMIT = 5
RATE_WINDOW = 60.0


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="frankenstein-session")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def password_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.dashboard_password_hash.strip())


def verify_password(password: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    stored = settings.dashboard_password_hash.strip()
    if not stored:
        # No hash configured: accept any non-empty password so first boot is usable.
        # main.py logs a loud warning about this at startup.
        return bool(password)
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:
        log.error("DASHBOARD_PASSWORD_HASH is not a valid bcrypt hash")
        return False


def check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    q = _attempts[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts, wait a minute")
    q.append(now)


def _secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def set_session_cookie(request: Request, response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    token = _serializer(settings).dumps({"kind": "session"})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )


def set_kiosk_cookie(request: Request, response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    token = _serializer(settings).dumps({"kind": "kiosk"})
    response.set_cookie(
        KIOSK_COOKIE,
        token,
        max_age=365 * 86400,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )


def clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(KIOSK_COOKIE, path="/")


def _read(request: Request, cookie: str, kind: str, max_age: int) -> bool:
    raw = request.cookies.get(cookie)
    if not raw:
        return False
    try:
        payload = _serializer(get_settings()).loads(raw, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and payload.get("kind") == kind


def has_session(request: Request) -> bool:
    return _read(request, SESSION_COOKIE, "session", get_settings().session_days * 86400)


def has_kiosk(request: Request) -> bool:
    settings = get_settings()
    if not settings.kiosk_token:
        return False
    return _read(request, KIOSK_COOKIE, "kiosk", 365 * 86400)


def kiosk_token_valid(token: str | None) -> bool:
    settings = get_settings()
    if not token or not settings.kiosk_token:
        return False
    return hmac.compare_digest(token, settings.kiosk_token)


def auth_mode(request: Request) -> str | None:
    if has_session(request):
        return "session"
    if has_kiosk(request):
        return "kiosk"
    return None


async def require_read(request: Request) -> str:
    mode = auth_mode(request)
    if mode is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return mode


async def require_write(request: Request) -> str:
    if has_session(request):
        return "session"
    if has_kiosk(request):
        raise HTTPException(status_code=403, detail="Kiosk sessions are read only")
    raise HTTPException(status_code=401, detail="Not authenticated")
