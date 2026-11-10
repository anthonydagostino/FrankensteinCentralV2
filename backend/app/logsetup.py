"""Logging configuration with a redaction filter so secrets never reach logs."""

from __future__ import annotations

import logging
import re
from typing import Any

_PATTERNS = [
    re.compile(r"(X-Plex-Token=)[^&\s\"']+", re.I),
    re.compile(r"(Authorization[\"']?\s*[:=]\s*[\"']?)(Bearer\s+)?[^\s\"',}]+", re.I),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I),
    re.compile(r"(/calendar/ical/)[^\s\"']+", re.I),
    re.compile(r"(secret=)[^&\s\"']+", re.I),
    re.compile(r"(token=)[^&\s\"']+", re.I),
]


class RedactingFilter(logging.Filter):
    """Replaces token patterns and literal secret values with [redacted] in log records."""

    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self.secrets = sorted({s for s in (secrets or []) if s}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for pat in _PATTERNS:
            text = pat.sub(lambda m: (m.group(1) or "") + "[redacted]", text)
        for secret in self.secrets:
            if secret in text:
                text = text.replace(secret, "[redacted]")
        return text

    def _redact_value(self, value: Any) -> Any:
        return self.redact(value) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        # args are redacted in place rather than folded into msg: uvicorn's access formatter unpacks them by position
        if isinstance(record.args, tuple):
            record.args = tuple(self._redact_value(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._redact_value(v) for k, v in record.args.items()}
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.exc_info:
            # tracebacks carry request URLs (httpx errors), so they are rendered and redacted here
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


# One process wide filter; install_redaction() loads the secrets into it and attaches it to the loggers.
_filter = RedactingFilter()


def install_redaction(secrets: list[str]) -> RedactingFilter:
    """Attach the filter to every handler we know about, including uvicorn's."""
    flt = _filter
    flt.secrets = sorted({s for s in secrets if s}, key=len, reverse=True)
    loggers = [
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
        logging.getLogger("uvicorn.error"),
        logging.getLogger("frankenstein"),
    ]
    for lg in loggers:
        lg.addFilter(flt)
        for h in lg.handlers:
            h.addFilter(flt)
    return flt


def redact_text(text: str) -> str:
    """Redact known secrets and token shaped fragments from free text (used for envelope error messages)."""
    return _filter.redact(text)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
