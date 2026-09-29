"""openEHR adapter: renders AQL against the laboratory result archetype."""

from __future__ import annotations

from datetime import datetime

from ..sources import openehr_cdr
from .base import Adapter, AdapterResponse, RawRecord, SubRequest

_AQL = """SELECT
  c/uid/value AS uid,
  a/items[at0024]/value/defining_code/code_string AS analyte,
  a/items[at0001]/value/magnitude AS magnitude,
  a/items[at0001]/value/units AS units,
  o/data[at0001]/events[at0002]/time/value AS time
FROM EHR e[ehr_id/value=$ehrId]
  CONTAINS COMPOSITION c
    CONTAINS OBSERVATION o[openEHR-EHR-OBSERVATION.laboratory_test_result.v1]
      CONTAINS CLUSTER a[openEHR-EHR-CLUSTER.laboratory_test_analyte.v1]
WHERE a/items[at0024]/value/defining_code/code_string MATCHES {{{codes}}}
  AND o/data[at0001]/events[at0002]/time/value >= $from
  AND o/data[at0001]/events[at0002]/time/value <= $to
ORDER BY o/data[at0001]/events[at0002]/time/value"""


class OpenEhrAqlAdapter(Adapter):
    interface = "openehr-aql"

    def _codes(self, sub: SubRequest) -> dict[str, str]:
        return {b.instance_variable["native"]["analyte_code"]: b.instance_variable["id"] for b in sub.bindings}

    def plan(self, sub: SubRequest) -> list[str]:
        codes = ", ".join(f"'{c}'" for c in self._codes(sub))
        aql = _AQL.format(codes=codes)
        return [f"POST /openehr/v1/query/aql\n-- $ehrId={sub.local_id}  $from={sub.effective_from.isoformat()}  $to={sub.effective_to.isoformat()}\n{aql}"]

    async def execute(self, sub: SubRequest) -> AdapterResponse:
        code_to_iv = self._codes(sub)
        aql = _AQL.format(codes=", ".join(f"'{c}'" for c in code_to_iv))
        params = {"ehrId": sub.local_id, "codes": list(code_to_iv), "from": sub.effective_from, "to": sub.effective_to}
        resp = await openehr_cdr.execute_aql(aql, params, sub.context)
        records = [
            RawRecord(
                instance_variable=code_to_iv[r["analyte"]],
                value=r["magnitude"],
                unit=r["units"],
                effective=r["time"] if isinstance(r["time"], datetime) else datetime.fromisoformat(r["time"]),
                recorded=r["committed"],
                record_id=r["uid"],
                native={"archetype": openehr_cdr.ARCHETYPE, "composition_uid": r["uid"], "DV_QUANTITY": {"magnitude": r["magnitude"], "units": r["units"]}},
            )
            for r in resp["rows"]
        ]
        return AdapterResponse(records, resp["withheld"], resp["decision"], self.plan(sub))
