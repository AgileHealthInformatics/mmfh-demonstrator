"""Federation Broker.

Turns a Logical Information Request into native sub-requests using the
catalogue, executes them in parallel under a deadline, and reassembles the
answers with provenance, equivalence grades and explicit completeness.

The broker is stateless with respect to clinical content: it holds plans,
not data. Steps follow the design:
  validate -> pre-filter policy -> resolve identity -> resolve semantics ->
  localise -> plan -> execute -> integrate -> report -> audit
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from . import audit, transforms
from .adapters import REGISTRY, AdapterResponse, SubRequest
from .catalogue import Catalogue, VariableBinding
from .identity import IdentityIndex, IdentityLink
from .models import (
    ExcludedSource,
    FederatedResult,
    LogicalInformationRequest,
    ResultItem,
    SourceReport,
    SourceStatus,
    TransformStep,
)
from .policy import pre_filter, request_context
from .sources.common import SourceRefused


class RequestRejected(ValueError):
    """The LIR itself is invalid (unknown purpose, subject or concept)."""


@dataclass
class _Planned:
    source_id: str
    link: IdentityLink
    bindings: list[VariableBinding]
    unresolved: list[str]
    sub: SubRequest
    native_queries: list[str] = field(default_factory=list)


class FederationBroker:
    def __init__(self, catalogue: Catalogue, index: IdentityIndex):
        self.catalogue = catalogue
        self.index = index
        self._plan_cache: dict[tuple, list[str]] = {}

    # ------------------------------------------------------------------
    def _validate(self, lir: LogicalInformationRequest) -> None:
        cat = self.catalogue
        if lir.purpose not in cat.purposes:
            raise RequestRejected(f"Unknown purpose '{lir.purpose}'. Allowed: {', '.join(cat.purposes)}")
        if not self.index.known(lir.subject):
            raise RequestRejected(f"Subject '{lir.subject}' is not in the identity index")
        unknown = [c for c in lir.concepts if c not in cat.concepts]
        if unknown:
            raise RequestRejected(f"Unknown concept(s): {', '.join(unknown)}")

    # ------------------------------------------------------------------
    async def handle(self, lir: LogicalInformationRequest) -> FederatedResult:
        self._validate(lir)
        cat = self.catalogue
        request_id = str(uuid.uuid4())
        started = datetime.now(timezone.utc)
        ctx = request_context(lir, request_id)
        accept = set(lir.accept_grades)
        t_from = lir.window.effective_from.astimezone(timezone.utc)
        t_to = (lir.window.effective_to or started).astimezone(timezone.utc)

        reports: dict[str, SourceReport] = {}
        excluded: list[ExcludedSource] = []
        warnings: list[str] = []

        # Candidate sources: registered sources exposing at least one requested concept.
        candidates = [
            sid for sid in cat.sources if any(cat.exposes_concept(c, sid) for c in lir.concepts)
        ]

        def rep(sid: str, status: SourceStatus, detail: str) -> None:
            s = cat.sources[sid]
            reports[sid] = SourceReport(
                source=sid, label=s["label"], interface=s["capability"]["interface"], status=status, detail=detail
            )

        # 2. Policy pre-filter (before any identity lookup)
        allowed: list[str] = []
        for sid in candidates:
            d = pre_filter(cat, lir, sid)
            if d.allowed:
                allowed.append(sid)
            else:
                rep(sid, SourceStatus.not_asked, f"Excluded at pre-filter: {d.reason}")

        # 3. Identity resolution (P4: links to undescribed sources are refused)
        links = {}
        for link in self.index.resolve(lir.subject, lir.purpose):
            if not cat.is_registered(link.source):
                excluded.append(
                    ExcludedSource(
                        source=link.source,
                        reason="Holds records for this person but is not described in the catalogue (P4: metadata before data)",
                    )
                )
                continue
            links[link.source] = link
        threshold = cat.identity_thresholds.get(lir.purpose, 1.0)

        # 4-6. Semantics, localise, plan
        planned: list[_Planned] = []
        for sid in allowed:
            link = links.get(sid)
            if link is None:
                rep(sid, SourceStatus.not_asked, "Identity index records no data for this person at this source")
                continue
            if link.confidence < threshold:
                rep(
                    sid,
                    SourceStatus.identity_uncertain,
                    f"{link.method} link confidence {link.confidence:.2f} below {threshold:.2f} threshold for {lir.purpose}",
                )
                continue
            bindings: list[VariableBinding] = []
            unresolved: list[str] = []
            for c in lir.concepts:
                b, u = cat.bindings_for(c, sid, accept)
                bindings += b
                unresolved += u
            if not bindings:
                if unresolved:
                    rep(sid, SourceStatus.semantics_unresolved, "Source may hold relevant data but no approved mapping exists")
                    reports[sid].unresolved_variables = unresolved
                else:
                    rep(sid, SourceStatus.not_asked, "No variables at the accepted equivalence grades")
                continue
            sub = SubRequest(sid, link.local_id, bindings, t_from, t_to, ctx)
            adapter = REGISTRY[cat.sources[sid]["capability"]["interface"]]
            key = (cat.version, sid, tuple(sorted(b.instance_variable["id"] for b in bindings)), t_from, t_to, link.local_id)
            if key not in self._plan_cache:
                self._plan_cache[key] = adapter.plan(sub)
            planned.append(_Planned(sid, link, bindings, unresolved, sub, self._plan_cache[key]))

        # 7. Execute in parallel under the deadline
        async def run(p: _Planned) -> tuple[_Planned, Any, int]:
            adapter = REGISTRY[cat.sources[p.source_id]["capability"]["interface"]]
            t0 = time.perf_counter()
            try:
                resp = await asyncio.wait_for(adapter.execute(p.sub), timeout=lir.deadline_seconds)
            except BaseException as e:  # noqa: BLE001 - every failure must be reported, never swallowed
                if isinstance(e, asyncio.CancelledError):
                    e = asyncio.TimeoutError()
                resp = e
            return p, resp, int((time.perf_counter() - t0) * 1000)

        outcomes = await asyncio.gather(*(run(p) for p in planned))

        # 8. Integrate
        retrieved_at = datetime.now(timezone.utc)
        items: list[ResultItem] = []
        for p, resp, ms in outcomes:
            sid = p.source_id
            src = cat.sources[sid]
            r = SourceReport(
                source=sid,
                label=src["label"],
                interface=src["capability"]["interface"],
                status=SourceStatus.complete,
                native_queries=p.native_queries,
                unresolved_variables=p.unresolved,
                elapsed_ms=ms,
            )
            reports[sid] = r
            if isinstance(resp, SourceRefused):
                r.status, r.detail = SourceStatus.not_permitted, f"Source refused: {resp}"
                continue
            if isinstance(resp, asyncio.TimeoutError):
                r.status, r.detail = SourceStatus.unavailable, f"No response within {lir.deadline_seconds:g}s deadline; retry offered"
                continue
            if isinstance(resp, Exception):
                r.status, r.detail = SourceStatus.failed, f"Adapter or source error: {type(resp).__name__}: {resp}"
                continue

            assert isinstance(resp, AdapterResponse)
            by_iv = {b.instance_variable["id"]: b for b in p.bindings}
            src_items, dropped = self._integrate(lir, sid, p.link, by_iv, resp, retrieved_at)
            items += src_items
            r.items_returned = len(src_items)
            notes = []
            if resp.withheld:
                notes.append(f"{resp.withheld} entr{'y' if resp.withheld == 1 else 'ies'} withheld by source policy")
            if dropped:
                notes.append(f"{dropped} value(s) excluded: mapping condition not met")
            if p.unresolved:
                notes.append(f"{len(p.unresolved)} variable(s) without an approved mapping")
            if resp.withheld or p.unresolved:
                r.status = SourceStatus.partial
            elif not src_items:
                r.status = SourceStatus.no_matching_data
            r.detail = "; ".join(notes) or ("Answered fully" if src_items else "Answered; nothing matched")

        self._flag_duplicates(items)
        items.sort(key=lambda i: (i.concept, i.effective_time))

        # 9. Report
        ok = {SourceStatus.complete, SourceStatus.no_matching_data}
        asked = [r for r in reports.values() if r.status != SourceStatus.not_asked]
        overall = "complete" if all(r.status in ok for r in asked) else "partial"
        if any(i.match_method == "probabilistic" for i in items):
            warnings.append("Some items are linked to the subject by a probabilistic identity match")
        if excluded:
            warnings.append(f"{len(excluded)} source(s) known to hold data were not queried because they are not described in the catalogue")

        result = FederatedResult(
            request_id=request_id,
            catalogue_version=cat.version,
            purpose=lir.purpose,
            subject=lir.subject,
            overall_status=overall,
            items=items,
            sources=sorted(reports.values(), key=lambda r: list(cat.sources).index(r.source)),
            excluded=excluded,
            warnings=warnings,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
        )

        # 10. Audit (plans and decisions, no clinical values)
        audit.record(
            {
                "request_id": request_id,
                "catalogue_version": cat.version,
                "requester": lir.requester.model_dump(),
                "purpose": lir.purpose,
                "break_glass": lir.break_glass,
                "subject": lir.subject,
                "concepts": lir.concepts,
                "sources": [
                    {"source": r.source, "status": r.status.value, "items": r.items_returned, "detail": r.detail, "native_queries": r.native_queries}
                    for r in result.sources
                ],
                "excluded": [e.model_dump() for e in excluded],
                "overall_status": overall,
                "item_count": len(items),
            }
        )
        return result

    # ------------------------------------------------------------------
    def _integrate(
        self,
        lir: LogicalInformationRequest,
        sid: str,
        link: IdentityLink,
        by_iv: dict[str, VariableBinding],
        resp: AdapterResponse,
        retrieved_at: datetime,
    ) -> tuple[list[ResultItem], int]:
        cat = self.catalogue
        src = cat.sources[sid]
        out: list[ResultItem] = []
        dropped = 0
        for n, rec in enumerate(resp.records):
            b = by_iv[rec.instance_variable]
            m, rv = b.mapping, b.represented_variable
            rule = m.get("condition_rule")
            if rule and getattr(rec, rule["field"], None) not in rule["in"]:
                dropped += 1
                continue

            chain = [
                TransformStep(
                    kind="mapping",
                    id=m["id"],
                    version=m["version"],
                    detail=f"{rec.instance_variable} -> {m['to_concept']} ({m['grade']})"
                    + (f"; condition: {m['conditions']}" if m.get("conditions") else ""),
                )
            ]
            rendered_value: Optional[Any] = None
            rendered_unit: Optional[str] = None
            flags: list[str] = []
            if lir.render_units and rv.get("value_domain") == "quantity":
                target = cat.preferred_unit(m["to_concept"])
                t = None
                if m.get("transformation"):
                    t = cat.transformations[m["transformation"]]
                elif target and rec.unit != target:
                    t = transforms.unit_conversion_for(cat.transformations, rec.unit, target)
                if t and t.get("to_unit") == target:
                    rendered_value = transforms.apply(t, rec.value)
                    rendered_unit = target
                    chain.append(TransformStep(kind="transformation", id=t["id"], version=t["version"], detail=t["description"]))
                    flags.append("derived")
                else:
                    rendered_value, rendered_unit = rec.value, rec.unit

            if link.method == "probabilistic":
                flags.append("probabilistic-identity")
            notes = cat.related_notes(rv["id"])
            if m.get("note"):
                notes.insert(0, m["note"])

            out.append(
                ResultItem(
                    item_id=f"{sid}:{n}",
                    concept=m["to_concept"],
                    concept_label=cat.concepts[m["to_concept"]]["label"],
                    grade=b.grade,
                    represented_variable=rv["id"],
                    represented_label=rv["label"],
                    native_value=rec.value,
                    native_unit=rec.unit,
                    native_representation=(
                        {**rec.native, "accession": rec.accession}
                        if lir.provenance_depth == "full"
                        else {"instance_variable": rec.instance_variable, "accession": rec.accession}
                    ),
                    rendered_value=rendered_value,
                    rendered_unit=rendered_unit,
                    subject=lir.subject,
                    match_method=link.method,
                    match_confidence=link.confidence,
                    effective_time=rec.effective,
                    recorded_time=rec.recorded,
                    source=sid,
                    source_record_id=rec.record_id,
                    authority_status=src["authority_status"],
                    transformation_chain=chain,
                    quality=list(src.get("quality", [])),
                    retrieved_at=retrieved_at,
                    flags=flags,
                    notes=notes,
                )
            )
        return out, dropped

    # ------------------------------------------------------------------
    @staticmethod
    def _flag_duplicates(items: list[ResultItem]) -> None:
        """Flag probable duplicates across sources; never merge silently.

        Key: shared accession number for the same concept, or the same concept,
        effective time and value from different sources. Differing values under
        the same key are flagged as conflicts.
        """
        groups: dict[tuple, list[ResultItem]] = defaultdict(list)
        for it in items:
            acc = it.native_representation.get("accession")
            if acc:
                groups[("acc", it.concept, it.represented_variable if it.concept == "concept:egfr" else "", acc)].append(it)
        for key, group in groups.items():
            if len({i.source for i in group}) < 2:
                continue
            comparable = {
                (i.rendered_unit or i.native_unit, round(float(i.rendered_value if i.rendered_value is not None else i.native_value), 0))
                for i in group
            }
            units = {u for u, _ in comparable}
            for it in group:
                others = [o.item_id for o in group if o is not it]
                it.flags.append("possible-duplicate")
                it.notes.append(f"Probable duplicate of {', '.join(others)} (shared accession {key[-1]})")
                if len(units) > 1:
                    it.notes.append("Values held in different units; request unit rendering to compare")
                elif len(comparable) > 1:
                    it.flags.append("conflict")
                    it.notes.append("Values differ between sources for the same event")
                if it.authority_status.startswith("authoritative"):
                    it.flags.append("authoritative-copy")
