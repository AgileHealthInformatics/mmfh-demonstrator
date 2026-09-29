"""Research repository: a curated, DDI-CDI described dataset behind a dataset API.

Keyed by pseudonym only. Answers research purposes only.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..policy import verify_context
from .common import SourceRefused, days_ago

DATASET = {
    "id": "RENAL-COHORT-2025",
    "records": [
        {"pseudonym": "PSN-RC25-0042", "EGFR_21": 55, "OBS_DATE": days_ago(330), "ROW": "r-0042-01"},
        {"pseudonym": "PSN-RC25-0042", "EGFR_21": 49, "OBS_DATE": days_ago(150), "ROW": "r-0042-02"},
    ],
}


async def dataset_query(request: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.1)
    if not verify_context(ctx):
        raise SourceRefused("Request context signature invalid")
    if ctx["purpose"] != "research":
        raise SourceRefused("Research repository answers research purposes only")
    rows = [
        r
        for r in DATASET["records"]
        if r["pseudonym"] == request["pseudonym"] and request["from"] <= r["OBS_DATE"] <= request["to"]
    ]
    return {"dataset": DATASET["id"], "variables": request["variables"], "rows": rows, "withheld": 0, "decision": "permit"}
