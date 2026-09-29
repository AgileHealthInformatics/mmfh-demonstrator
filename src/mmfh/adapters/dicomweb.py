"""DICOMweb adapter: QIDO-RS study search plus report retrieval."""

from __future__ import annotations

from urllib.parse import urlencode

from ..sources import imaging
from .base import Adapter, AdapterResponse, RawRecord, SubRequest

BASE = "https://imaging.demo/dicomweb"


class DicomWebReportsAdapter(Adapter):
    interface = "dicomweb-reports"

    def _url(self, sub: SubRequest) -> str:
        mods = sorted({b.instance_variable["native"]["modality"] for b in sub.bindings})
        params = [
            ("PatientID", sub.local_id),
            ("ModalitiesInStudy", ",".join(mods)),
            ("StudyDate", f"{sub.effective_from:%Y%m%d}-{sub.effective_to:%Y%m%d}"),
            ("includefield", "StudyDescription"),
        ]
        return f"{BASE}/studies?{urlencode(params)}"

    def plan(self, sub: SubRequest) -> list[str]:
        return ["GET " + self._url(sub), "GET {study}/reports (per matched study)"]

    async def execute(self, sub: SubRequest) -> AdapterResponse:
        iv = sub.bindings[0].instance_variable
        resp = await imaging.qido_with_reports(self._url(sub), sub.context)
        records = [
            RawRecord(
                instance_variable=iv["id"],
                value=s["report"],
                unit=None,
                effective=s["study_date"],
                recorded=None,
                record_id=f"{BASE}/studies/{s['study_uid']}",
                native=s,
            )
            for s in resp["studies"]
            if sub.effective_from <= s["study_date"] <= sub.effective_to
        ]
        return AdapterResponse(records, resp["withheld"], resp["decision"], self.plan(sub))
