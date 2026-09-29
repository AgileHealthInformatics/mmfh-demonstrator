"""Community provider: a relational clinical application behind a governed SQL service.

The adapter never touches the operational database directly. It calls a
parameterised query service; the service executes it against SQLite and
applies the provider's own restrictions (patient-requested restrictions are
withheld and counted, not silently dropped).
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from typing import Any

from ..policy import verify_context
from .common import SourceRefused, days_ago

_DDL = """
CREATE TABLE LAB_RESULTS (
    RESULT_ID    TEXT PRIMARY KEY,
    PATIENT_ID   TEXT NOT NULL,
    TEST_CODE    TEXT NOT NULL,
    CREAT_MGDL   REAL,
    ACR_VAL      REAL,
    SPECIMEN     TEXT,
    COLLECTED_AT TEXT NOT NULL,
    RECORDED_AT  TEXT NOT NULL,
    ACCESSION    TEXT,
    RESTRICTED   INTEGER NOT NULL DEFAULT 0
);
"""

# (id, patient, test, creat_mgdl, acr, specimen, days_ago, accession, restricted)
_SEED = [
    ("LR-1001", "C-000913", "CREAT", 1.30, None, "SERUM", 150, "ACC-2026-1650", 0),
    ("LR-1002", "C-000913", "CREAT", 1.35, None, "SERUM", 90, "ACC-2026-1902", 1),  # patient restriction
    ("LR-1003", "C-000913", "CREAT", 1.40, None, None, 60, "ACC-2026-2240", 0),  # same lab result as Hospital B
    ("LR-1004", "C-000913", "ACR", None, 5.5, "URINE", 90, "ACC-2026-1903", 0),
    ("LR-2001", "C-001204", "CREAT", 0.95, None, "SERUM", 30, "ACC-2026-2410", 0),
]

_ALLOWED_SQL = re.compile(r"^\s*SELECT\s.+\sFROM\s+LAB_RESULTS\s+WHERE\s", re.IGNORECASE | re.DOTALL)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(_DDL)
    con.executemany(
        "INSERT INTO LAB_RESULTS VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (rid, pat, test, cr, acr, spec, days_ago(d).isoformat(), days_ago(d, hour=17).isoformat(), acc, res)
            for rid, pat, test, cr, acr, spec, d, acc, res in _SEED
        ],
    )
    return con


_DB = _connect()


async def query_service(sql: str, params: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.12)
    if not verify_context(ctx):
        raise SourceRefused("Request context signature invalid")
    if ctx["purpose"] != "direct-care":
        raise SourceRefused("Community provider answers direct-care requests only")
    if not _ALLOWED_SQL.match(sql) or ";" in sql:
        raise SourceRefused("Query not permitted by governed service: only parameterised SELECTs on LAB_RESULTS")

    rows = [dict(r) for r in _DB.execute(sql, params).fetchall()]
    if rows and "RESULT_ID" not in rows[0]:
        raise SourceRefused("Governed service requires RESULT_ID in the projection")
    # Restrictions are enforced by the service itself, not trusted to the caller.
    restricted = {r[0] for r in _DB.execute("SELECT RESULT_ID FROM LAB_RESULTS WHERE RESTRICTED = 1")}
    released = [r for r in rows if r["RESULT_ID"] not in restricted]
    withheld = len(rows) - len(released)
    for r in released:
        r.pop("RESTRICTED", None)
    return {
        "rows": released,
        "withheld": withheld,
        "decision": "permit-with-redaction" if withheld else "permit",
        "withheld_reason": "patient-requested restriction" if withheld else None,
    }
