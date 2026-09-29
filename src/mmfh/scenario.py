"""The worked renal-function scenario from the design, as a ready-made LIR."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Grade, LogicalInformationRequest, Requester, TimeWindow


def renal_lir(**overrides) -> LogicalInformationRequest:
    now = datetime.now(timezone.utc)
    base = dict(
        subject="NID-DEMO-0001",
        concepts=["concept:egfr", "concept:serum-creatinine", "concept:uacr", "concept:renal-imaging-report"],
        window=TimeWindow(effective_from=now - timedelta(days=548)),
        accept_grades=[Grade.exact, Grade.narrower],
        render_units=True,
        purpose="direct-care",
        requester=Requester(id="clin-0042", role="consultant-nephrologist", organisation="Hospital A"),
        provenance_depth="full",
        deadline_seconds=2.0,
    )
    base.update(overrides)
    return LogicalInformationRequest(**base)
