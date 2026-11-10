"""Background refresh loops: one asyncio task per integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable

from .cache import Cache
from .integrations.base import BaseIntegration, Degraded, describe_error
from .logsetup import redact_text

log = logging.getLogger("frankenstein.scheduler")

MAX_BACKOFF = 600


class Scheduler:
    """Runs each integration on its own interval with exponential backoff (capped) after failures."""

    def __init__(self, cache: Cache):
        self.cache = cache
        self.integrations: dict[str, BaseIntegration] = {}
        self.after_success: dict[str, list[Callable[[], Awaitable[None] | None]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._wake: dict[str, asyncio.Event] = {}
        self._stopping = False

    def register(self, integration: BaseIntegration) -> None:
        """Add an integration and tell the cache about it; mocked integrations count as configured."""
        self.integrations[integration.name] = integration
        mocked = integration.is_mocked()
        self.cache.configure(
            integration.name, integration.interval_seconds, integration.is_configured() or mocked, integration.setup_hint(), source="mock" if mocked else "live"
        )

    def on_success(self, name: str, callback: Callable[[], Awaitable[None] | None]) -> None:
        """Run `callback` after every successful refresh of the named integration (sync or async)."""
        self.after_success.setdefault(name, []).append(callback)

    async def start(self) -> None:
        """Start one refresh loop task per registered integration."""
        self._stopping = False
        for name, integration in self.integrations.items():
            self._wake[name] = asyncio.Event()
            self._tasks[name] = asyncio.create_task(self._loop(integration), name=f"refresh:{name}")

    async def stop(self) -> None:
        """Cancel every refresh loop and wait for the tasks to finish."""
        self._stopping = True
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

    def trigger(self, name: str) -> None:
        """Ask a loop to refresh as soon as possible."""
        ev = self._wake.get(name)
        if ev:
            ev.set()

    async def refresh_once(self, integration: BaseIntegration) -> bool:
        """Run one refresh and store the result. Returns True on success or degraded."""
        name = integration.name
        mocked = integration.is_mocked()
        if not mocked and not integration.is_configured():
            self.cache.set_disabled(name, integration.setup_hint())
            return False
        try:
            source = "mock" if mocked else "live"
            if mocked:
                data = integration.mock()
            else:
                data = await integration.fetch()
            self.cache.set_ok(name, data, source=source)
            await self._run_callbacks(name)
            return True
        except Degraded as deg:
            self.cache.set_degraded(name, deg.data, deg.message, source="mock" if mocked else "live")
            log.warning("%s degraded: %s", name, redact_text(deg.message))
            await self._run_callbacks(name)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = describe_error(exc, name)
            self.cache.set_error(name, message)
            log.warning("%s refresh failed: %s", name, redact_text(message))
            return False

    async def _run_callbacks(self, name: str) -> None:
        for cb in self.after_success.get(name, []):
            try:
                result = cb()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # callbacks must never kill the loop
                log.exception("post refresh callback for %s failed: %s", name, exc)

    async def _loop(self, integration: BaseIntegration) -> None:
        name = integration.name
        # jitter the first run so sources are not hit in lockstep
        await asyncio.sleep(random.random() * 2)
        while not self._stopping:
            ok = await self.refresh_once(integration)
            entry = self.cache.get(name)
            failures = entry.attempts_failed if entry else 0
            base = (
                integration.interval_seconds
                if ok or (entry and entry.status == "disabled")
                else min(integration.interval_seconds * (2 ** min(failures, 6)), MAX_BACKOFF)
            )
            delay = base * (0.9 + random.random() * 0.2)  # jitter so sources are not polled in lockstep
            ev = self._wake[name]
            ev.clear()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(ev.wait(), timeout=delay)
