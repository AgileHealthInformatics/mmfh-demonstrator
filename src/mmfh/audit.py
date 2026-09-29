"""Broker-side audit.

Records the plan, catalogue version, each source's decision and a summary of
the returned result set - correlated by request id with the source-side audit.
Holds no clinical values: the broker keeps plans, not data.
"""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any

_LOG: deque[dict[str, Any]] = deque(maxlen=500)


def record(event: dict[str, Any]) -> None:
    event = {"at": datetime.now(timezone.utc).isoformat(), **event}
    _LOG.append(event)
    path = os.environ.get("MMFH_AUDIT_FILE")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")


def recent(limit: int = 50) -> list[dict[str, Any]]:
    return list(_LOG)[-limit:][::-1]


def clear() -> None:
    _LOG.clear()
