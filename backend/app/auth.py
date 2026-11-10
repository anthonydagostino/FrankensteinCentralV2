"""Single user password auth with signed cookies, plus the read-only kiosk cookie."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .settings import Settings, get_settings

log = logging.getLogger("frankenstein.auth")

SESSION_COOKIE = "fc_session"
KIOSK_COOKIE = "fc_kiosk"

_attempts: dict[str, deque[float]] = defaultdict(deque)
RATE_LIMIT = 5
RATE_WINDOW = 60.0
KIOSK_MAX_AGE = 365 * 86400


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="frankenstein-session")


def hash_password(password: str) -> str:
    """bcrypt hash for DASHBOARD_PASSWORD_HASH (also used by the hash_password CLI)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def password_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.dashboard_password_hash.strip())


def verify_password(password: str, settings: Settings | None = None) -> bool:
    """Compare against DASHBOARD_PASSWORD_HASH. bcrypt takes ~100 ms of CPU, so call it with asyncio.to_thread."""
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
    """Sliding window of RATE_LIMIT login attempts per RATE_WINDOW seconds per client address."""
    now = time.monotonic()
    # drop other addresses' expired windows too, so the dict cannot grow without bound
    for other in [k for k, q in _attempts.items() if k != ip and (not q or now - q[-1] > RATE_WINDOW)]:
        del _attempts[other]
    q = _attempts[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts, wait a minute")
    q.append(now)


def _secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def _kiosk_fingerprint(settings: Settings) -> str:
    """Binds a kiosk cookie to the KIOSK_TOKEN it was issued for, so rotating the token revokes old cookies."""
    return hashlib.sha256(settings.kiosk_token.encode("utf-8")).hexdigest()[:16]


def _set_cookie(request: Request, response: Response, name: str, payload: dict, max_age: int, settings: Settings) -> None:
    response.set_cookie(name, _serializer(settings).dumps(payload), max_age=max_age, httponly=True, samesite="lax", secure=_secure(request), path="/")


def set_session_cookie(request: Request, response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    _set_cookie(request, response, SESSION_COOKIE, {"kind": "session"}, settings.session_days * 86400, settings)


def set_kiosk_cookie(request: Request, response: Response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    _set_cookie(request, response, KIOSK_COOKIE, {"kind": "kiosk", "fp": _kiosk_fingerprint(settings)}, KIOSK_MAX_AGE, settings)


def clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(KIOSK_COOKIE, path="/")


def _read(request: Request, cookie: str, max_age: int, settings: Settings) -> dict | None:
    """Verified payload of a signed cookie, or None when missing, tampered with, or older than max_age."""
    raw = request.cookies.get(cookie)
    if not raw:
        return None
    try:
        payload = _serializer(settings).loads(raw, max_age=max_age)
    except BadSignature:  # SignatureExpired is a subclass
        return None
    return payload if isinstance(payload, dict) else None


def has_session(request: Request) -> bool:
    settings = get_settings()
    payload = _read(request, SESSION_COOKIE, settings.session_days * 86400, settings)
    return payload is not None and payload.get("kind") == "session"


def has_kiosk(request: Request) -> bool:
    settings = get_settings()
    if not settings.kiosk_token:
        return False
    payload = _read(request, KIOSK_COOKIE, KIOSK_MAX_AGE, settings)
    return payload is not None and payload.get("kind") == "kiosk" and payload.get("fp") == _kiosk_fingerprint(settings)


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
