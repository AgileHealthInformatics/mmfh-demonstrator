"""Dataset API adapter for DDI-CDI described research datasets."""

from __future__ import annotations

import json

from ..sources import research
from .base import Adapter, AdapterResponse, RawRecord, SubRequest


class DatasetAdapter(Adapter):
    interface = "dataset-api"

    def _request(self, sub: SubRequest) -> dict:
        return {
            "dataset": sub.bindings[0].instance_variable["native"]["dataset"],
            "pseudonym": sub.local_id,
            "variables": [b.instance_variable["native"]["variable"] for b in sub.bindings],
            "from": sub.effective_from,
            "to": sub.effective_to,
        }

    def plan(self, sub: SubRequest) -> list[str]:
        r = self._request(sub)
        r["from"], r["to"] = r["from"].isoformat(), r["to"].isoformat()
        return ["POST /datasets/query\n" + json.dumps(r, indent=2)]

    async def execute(self, sub: SubRequest) -> AdapterResponse:
        var_to_iv = {b.instance_variable["native"]["variable"]: b.instance_variable["id"] for b in sub.bindings}
        resp = await research.dataset_query(self._request(sub), sub.context)
        records = []
        for row in resp["rows"]:
            for var, iv_id in var_to_iv.items():
                if row.get(var) is None:
                    continue
                records.append(
                    RawRecord(
                        instance_variable=iv_id,
                        value=row[var],
                        unit="mL/min/{1.73_m2}",
                        effective=row["OBS_DATE"],
                        recorded=None,
                        record_id=f"{resp['dataset']}/{row['ROW']}",
                        native={"dataset": resp["dataset"], "variable": var, "row": row["ROW"]},
                    )
                )
        return AdapterResponse(records, 0, resp["decision"], self.plan(sub))
