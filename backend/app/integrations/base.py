"""Integration contract and shared HTTP helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from ..config_loader import DashboardConfig
from ..settings import Settings

log = logging.getLogger("frankenstein.integrations")

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class Degraded(Exception):
    """Raised by fetch() when only part of the data could be loaded."""

    def __init__(self, data: dict, message: str):
        super().__init__(message)
        self.data = data
        self.message = message


class TokenRejected(Exception):
    """401 or 403 from a service: do not retry, tell the user to fix the token."""


class NotConfigured(Exception):
    pass


@runtime_checkable
class Integration(Protocol):
    name: str
    interval_seconds: int

    def is_configured(self) -> bool: ...
    async def fetch(self) -> dict: ...
    def mock(self) -> dict: ...


class BaseIntegration:
    name: str = "base"
    interval_seconds: int = 300
    required_env: list[str] = []

    def __init__(self, settings: Settings, config: DashboardConfig):
        self.settings = settings
        self.config = config

    def is_configured(self) -> bool:
        return all(bool(getattr(self.settings, var.lower(), "") or self.settings.env_value(var)) for var in self.required_env)

    def is_mocked(self) -> bool:
        return self.settings.is_mocked(self.name)

    def setup_hint(self) -> list[str]:
        return list(self.required_env)

    async def fetch(self) -> dict:  # pragma: no cover - overridden
        raise NotImplementedError

    def mock(self) -> dict:  # pragma: no cover - overridden
        raise NotImplementedError


def load_fixture(name: str) -> Any:
    path = FIXTURES / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# HTTP helpers
# --------------------------------------------------------------------------
DEFAULT_TIMEOUT = 10.0


def make_client(timeout: float = DEFAULT_TIMEOUT, **kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, **kwargs)


async def request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    service: str = "service",
    **kwargs: Any,
) -> httpx.Response:
    """Request with retries on 5xx and network errors. 401/403 raise TokenRejected immediately."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt) + random.random() * 0.3)
                continue
            raise ConnectionError(f"{service} unreachable: {exc.__class__.__name__}") from exc
        if resp.status_code in (401, 403):
            raise TokenRejected(f"{service}: token rejected, regenerate it and update .env")
        if resp.status_code >= 500 and attempt < retries:
            last_exc = httpx.HTTPStatusError(f"{resp.status_code}", request=resp.request, response=resp)
            await asyncio.sleep(0.5 * (2**attempt) + random.random() * 0.3)
            continue
        return resp
    assert last_exc is not None
    raise last_exc


def describe_error(exc: Exception, service: str = "service") -> str:
    """Short, secret free message for the envelope."""
    if isinstance(exc, TokenRejected):
        return str(exc)
    if isinstance(exc, Degraded):
        return exc.message
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{service} returned HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return f"{service} timed out"
    if isinstance(exc, httpx.TransportError):
        return f"{service} unreachable"
    if isinstance(exc, ConnectionError):
        return str(exc)
    text = f"{exc.__class__.__name__}: {exc}"
    return text[:200]
