"""Shared helpers for mock sources."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def days_ago(n: int, hour: int = 9) -> datetime:
    d = NOW - timedelta(days=n)
    return d.replace(hour=hour, minute=0, second=0)


class SourceRefused(Exception):
    """Raised when a source refuses a request under its own policy."""


class SourceError(Exception):
    """Raised when a source fails."""
