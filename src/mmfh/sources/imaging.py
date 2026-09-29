"""Imaging provider: mock DICOMweb QIDO-RS plus report retrieval.

Deliberately slow by default (MMFH_IMAGING_DELAY seconds, default 5) so the
demo shows a source reported as Unavailable rather than silently empty.
Set MMFH_IMAGING_DELAY=0.1 to see it answer.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ..policy import verify_context
from .common import SourceRefused, days_ago

STUDIES = [
    {
        "patient_id": "PACS-88321",
        "study_uid": "1.2.826.0.1.3680043.10.999.1001",
        "modality": "US",
        "body_part": "KIDNEY",
        "study_date": days_ago(210),
        "report": "Both kidneys normal size. Mild increase in cortical echogenicity bilaterally. No hydronephrosis.",
    }
]


def delay() -> float:
    try:
        return float(os.environ.get("MMFH_IMAGING_DELAY", "5"))
    except ValueError:
        return 5.0


async def qido_with_reports(url: str, ctx: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(delay())
    if not verify_context(ctx):
        raise SourceRefused("Request context signature invalid")
    if ctx["purpose"] != "direct-care":
        raise SourceRefused("Imaging provider answers direct-care requests only")
    from urllib.parse import parse_qs, urlsplit

    q = parse_qs(urlsplit(url).query)
    pid = q["PatientID"][0]
    return {
        "studies": [s for s in STUDIES if s["patient_id"] == pid and s["modality"] in q.get("ModalitiesInStudy", ["US"])],
        "withheld": 0,
        "decision": "permit",
    }
