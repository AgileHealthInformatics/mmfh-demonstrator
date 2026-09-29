"""Hospital B: a mock FHIR R4 server.

Parses a genuine FHIR search URL (Observation?patient=&code=&date=ge&date=le)
and returns a searchset Bundle of Observation resources.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from ..policy import verify_context
from .common import SourceRefused, days_ago

# (patient, loinc, value, unit, days_ago, accession)
_SEED = [
    ("PAT-B-55120", "14682-9", 118, "umol/L", 200, "ACC-2026-1181"),
    ("PAT-B-55120", "14682-9", 124, "umol/L", 60, "ACC-2026-2240"),
    ("PAT-B-55120", "62238-1", 51, "mL/min/{1.73_m2}", 200, "ACC-2026-1181"),
    ("PAT-B-55120", "62238-1", 48, "mL/min/{1.73_m2}", 60, "ACC-2026-2240"),
    ("PAT-B-55120", "98979-8", 50, "mL/min/{1.73_m2}", 60, "ACC-2026-2240"),
    ("PAT-B-60001", "14682-9", 88, "umol/L", 45, "ACC-2026-2301"),
]

OBSERVATIONS: list[dict[str, Any]] = [
    {
        "resourceType": "Observation",
        "id": f"obs-b-{i:04d}",
        "status": "final",
        "identifier": [{"system": "urn:demo:lab-accession", "value": acc}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
        "subject": {"reference": f"Patient/{pat}"},
        "effectiveDateTime": days_ago(d).isoformat(),
        "issued": days_ago(d, hour=16).isoformat(),
        "valueQuantity": {"value": val, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
    }
    for i, (pat, code, val, unit, d, acc) in enumerate(_SEED)
]


def _parse(url: str) -> dict[str, list[str]]:
    q: dict[str, list[str]] = {}
    for k, v in parse_qsl(urlsplit(url).query):
        q.setdefault(k, []).append(v)
    return q


async def search(url: str, ctx: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.08)
    if not verify_context(ctx):
        raise SourceRefused("Request context signature invalid")
    if ctx["purpose"] not in ("direct-care", "secondary-use"):
        raise SourceRefused("Purpose not accepted by Hospital B local policy")

    q = _parse(url)
    patient = q["patient"][0]
    codes = {c.split("|")[-1] for c in q["code"][0].split(",")}
    ge = le = None
    for d in q.get("date", []):
        if d.startswith("ge"):
            ge = datetime.fromisoformat(d[2:])
        elif d.startswith("le"):
            le = datetime.fromisoformat(d[2:])

    entries = []
    for o in OBSERVATIONS:
        if o["subject"]["reference"] != f"Patient/{patient}":
            continue
        if o["code"]["coding"][0]["code"] not in codes:
            continue
        eff = datetime.fromisoformat(o["effectiveDateTime"])
        if (ge and eff < ge) or (le and eff > le):
            continue
        entries.append({"fullUrl": f"https://hospital-b.demo/fhir/Observation/{o['id']}", "resource": o})
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}
