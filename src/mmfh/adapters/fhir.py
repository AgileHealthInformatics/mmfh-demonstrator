"""FHIR R4 adapter: renders a search URL by patient, LOINC code and date."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from ..sources import fhir_server
from .base import Adapter, AdapterResponse, RawRecord, SubRequest

BASE = "https://hospital-b.demo/fhir"


class FhirSearchAdapter(Adapter):
    interface = "fhir-r4-search"

    def _codes(self, sub: SubRequest) -> dict[str, str]:
        return {b.instance_variable["native"]["code"]: b.instance_variable["id"] for b in sub.bindings}

    def _url(self, sub: SubRequest) -> str:
        params = [
            ("patient", sub.local_id),
            ("code", ",".join(self._codes(sub))),
            ("date", "ge" + sub.effective_from.isoformat()),
            ("date", "le" + sub.effective_to.isoformat()),
            ("_count", "100"),
        ]
        return f"{BASE}/Observation?{urlencode(params)}"

    def plan(self, sub: SubRequest) -> list[str]:
        return ["GET " + self._url(sub)]

    async def execute(self, sub: SubRequest) -> AdapterResponse:
        code_to_iv = {k.split("|")[-1]: v for k, v in self._codes(sub).items()}
        bundle = await fhir_server.search(self._url(sub), sub.context)
        records = []
        for e in bundle.get("entry", []):
            o = e["resource"]
            code = o["code"]["coding"][0]["code"]
            acc = next((i["value"] for i in o.get("identifier", []) if "accession" in i["system"]), None)
            records.append(
                RawRecord(
                    instance_variable=code_to_iv[code],
                    value=o["valueQuantity"]["value"],
                    unit=o["valueQuantity"]["unit"],
                    effective=datetime.fromisoformat(o["effectiveDateTime"]),
                    recorded=datetime.fromisoformat(o["issued"]) if o.get("issued") else None,
                    record_id=e["fullUrl"],
                    accession=acc,
                    native=o,
                )
            )
        return AdapterResponse(records, 0, "permit", self.plan(sub))
