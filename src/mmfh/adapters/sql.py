"""Governed SQL service adapter: renders a parameterised SELECT."""

from __future__ import annotations

from datetime import datetime

from ..sources import community_sql
from .base import Adapter, AdapterResponse, RawRecord, SubRequest


class SqlServiceAdapter(Adapter):
    interface = "sql-service"

    def _build(self, sub: SubRequest) -> tuple[str, dict]:
        test_to_iv = {b.instance_variable["native"]["test_code"]: b.instance_variable for b in sub.bindings}
        cols = sorted({iv["native"]["column"] for iv in test_to_iv.values()})
        placeholders = ", ".join(f":t{i}" for i in range(len(test_to_iv)))
        sql = (
            "SELECT RESULT_ID, TEST_CODE, "
            + ", ".join(cols)
            + ", SPECIMEN, COLLECTED_AT, RECORDED_AT, ACCESSION "
            "FROM LAB_RESULTS WHERE PATIENT_ID = :pid "
            f"AND TEST_CODE IN ({placeholders}) "
            "AND COLLECTED_AT BETWEEN :from AND :to ORDER BY COLLECTED_AT"
        )
        params = {"pid": sub.local_id, "from": sub.effective_from.isoformat(), "to": sub.effective_to.isoformat()}
        for i, t in enumerate(test_to_iv):
            params[f"t{i}"] = t
        return sql, params

    def plan(self, sub: SubRequest) -> list[str]:
        sql, params = self._build(sub)
        return [f"POST /governed-query/LAB_RESULTS\n{sql}\n-- params: {params}"]

    async def execute(self, sub: SubRequest) -> AdapterResponse:
        test_to_iv = {b.instance_variable["native"]["test_code"]: b.instance_variable for b in sub.bindings}
        sql, params = self._build(sub)
        resp = await community_sql.query_service(sql, params, sub.context)
        records = []
        for r in resp["rows"]:
            iv = test_to_iv[r["TEST_CODE"]]
            col = iv["native"]["column"]
            records.append(
                RawRecord(
                    instance_variable=iv["id"],
                    value=r[col],
                    unit="mg/dL" if col == "CREAT_MGDL" else "mg/mmol",
                    effective=datetime.fromisoformat(r["COLLECTED_AT"]),
                    recorded=datetime.fromisoformat(r["RECORDED_AT"]),
                    record_id=f"LAB_RESULTS/{r['RESULT_ID']}",
                    accession=r["ACCESSION"],
                    native={"table": "LAB_RESULTS", **r},
                    specimen=r["SPECIMEN"],
                )
            )
        detail = f"{resp['withheld']} row(s) withheld: {resp['withheld_reason']}" if resp["withheld"] else ""
        return AdapterResponse(records, resp["withheld"], resp["decision"], self.plan(sub), detail)
