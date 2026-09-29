"""Hospital A: a mock openEHR Clinical Data Repository.

A real CDR would execute the AQL text it receives. This mock accepts the AQL
(for display and audit) plus its bound parameters, and evaluates the
parameters against in-memory compositions shaped like openEHR laboratory
results. It is honest about that in the response it returns.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from ..policy import verify_context
from .common import SourceRefused, days_ago

ARCHETYPE = "openEHR-EHR-OBSERVATION.laboratory_test_result.v1"

# (ehr_id, analyte LOINC, value, unit, days_ago)
_SEED = [
    ("ehr-7f3a9c", "14682-9", 90, "umol/L", 700),  # outside an 18-month window
    ("ehr-7f3a9c", "14682-9", 98, "umol/L", 520),
    ("ehr-7f3a9c", "14682-9", 105, "umol/L", 400),
    ("ehr-7f3a9c", "14682-9", 112, "umol/L", 250),
    ("ehr-7f3a9c", "14682-9", 121, "umol/L", 120),
    ("ehr-7f3a9c", "14682-9", 131, "umol/L", 30),
    ("ehr-7f3a9c", "98979-8", 62, "mL/min/{1.73_m2}", 520),
    ("ehr-7f3a9c", "98979-8", 57, "mL/min/{1.73_m2}", 400),
    ("ehr-7f3a9c", "98979-8", 52, "mL/min/{1.73_m2}", 250),
    ("ehr-7f3a9c", "98979-8", 47, "mL/min/{1.73_m2}", 120),
    ("ehr-7f3a9c", "98979-8", 43, "mL/min/{1.73_m2}", 30),
    ("ehr-7f3a9c", "32294-1", 3.1, "mg/mmol", 400),
    ("ehr-7f3a9c", "32294-1", 4.8, "mg/mmol", 120),
    ("ehr-7f3a9c", "32294-1", 6.2, "mg/mmol", 30),
]

COMPOSITIONS: list[dict[str, Any]] = [
    {
        "ehr_id": ehr,
        "composition_uid": f"a1b2c3d4-{i:04d}::hospital-a.demo::1",
        "archetype_id": ARCHETYPE,
        "analyte_code": code,
        "magnitude": val,
        "units": unit,
        "time": days_ago(d),
        "committed": days_ago(d, hour=14),
    }
    for i, (ehr, code, val, unit, d) in enumerate(_SEED)
]


async def execute_aql(aql: str, params: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.05)
    if not verify_context(ctx):
        raise SourceRefused("Request context signature invalid")
    if ctx["purpose"] not in ("direct-care", "secondary-use"):
        raise SourceRefused("Purpose not accepted by Hospital A local policy")

    ehr_id = params["ehrId"]
    codes = set(params["codes"])
    t_from: datetime = params["from"]
    t_to: datetime = params["to"]
    rows = [
        {
            "uid": c["composition_uid"],
            "analyte": c["analyte_code"],
            "magnitude": c["magnitude"],
            "units": c["units"],
            "time": c["time"],
            "committed": c["committed"],
        }
        for c in COMPOSITIONS
        if c["ehr_id"] == ehr_id and c["analyte_code"] in codes and t_from <= c["time"] <= t_to
    ]
    return {"q": aql, "rows": rows, "withheld": 0, "decision": "permit"}
