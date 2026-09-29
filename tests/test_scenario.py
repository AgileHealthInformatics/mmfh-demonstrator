"""Tests for the worked renal-function scenario and the design's principles.

Each test names the principle (P1-P12) or result-model rule it checks, so the
suite doubles as an executable reading of the architecture.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest

from mmfh.broker import FederationBroker, RequestRejected
from mmfh.catalogue import Catalogue
from mmfh.identity import IdentityIndex
from mmfh.models import Grade, SourceStatus
from mmfh.prov import to_prov
from mmfh.scenario import renal_lir


@pytest.fixture(scope="module")
def broker() -> FederationBroker:
    return FederationBroker(Catalogue.load(), IdentityIndex.load())


@pytest.fixture(scope="module")
def result(broker):
    return asyncio.run(broker.handle(renal_lir(deadline_seconds=1.0)))


def status(result, source):
    return next(s for s in result.sources if s.source == source).status


# -- The per-source outcome table from the design ---------------------------------
def test_scenario_per_source_outcome(result):
    assert status(result, "hospital-a") == SourceStatus.complete
    assert status(result, "hospital-b") == SourceStatus.complete
    assert status(result, "community") == SourceStatus.partial
    assert status(result, "imaging") == SourceStatus.unavailable
    assert status(result, "research") == SourceStatus.not_asked
    assert result.overall_status == "partial"


# -- P7: incompleteness is explicit -------------------------------------------------
def test_no_silent_empty_results(result):
    for s in result.sources:
        assert s.detail, f"{s.source} has no explanation for its status"
    imaging = next(s for s in result.sources if s.source == "imaging")
    assert imaging.items_returned == 0 and "deadline" in imaging.detail


def test_imaging_answers_when_deadline_allows(broker, monkeypatch):
    monkeypatch.setenv("MMFH_IMAGING_DELAY", "0.05")
    r = asyncio.run(broker.handle(renal_lir()))
    assert status(r, "imaging") == SourceStatus.complete
    assert any(i.concept == "concept:renal-imaging-report" for i in r.items)


# -- P8 / two-stage policy: pre-filter at broker, enforcement at source ----------
def test_research_excluded_by_purpose_before_identity(result):
    research = next(s for s in result.sources if s.source == "research")
    assert "pre-filter" in research.detail
    assert not research.native_queries


def test_source_side_redaction_is_reported(result):
    community = next(s for s in result.sources if s.source == "community")
    assert "withheld by source policy" in community.detail


def test_research_purpose_uses_pseudonym_only(broker):
    r = asyncio.run(broker.handle(renal_lir(purpose="research")))
    asked = [s for s in r.sources if s.status != SourceStatus.not_asked]
    assert [s.source for s in asked] == ["research"]
    assert all(i.match_method == "pseudonymous-linkage" for i in r.items)
    assert "PSN-RC25-0042" in r.sources[-1].native_queries[0]
    assert "NID-DEMO-0001" not in r.sources[-1].native_queries[0]


# -- P1 / P6: fidelity and provenance ------------------------------------------------
def test_unit_rendering_keeps_native_value(result):
    derived = [i for i in result.items if i.source == "community" and i.concept == "concept:serum-creatinine"]
    assert derived
    for i in derived:
        assert i.native_unit == "mg/dL" and i.rendered_unit == "umol/L"
        assert i.rendered_value == pytest.approx(i.native_value * 88.42, abs=0.1)
        kinds = [s.kind for s in i.transformation_chain]
        assert kinds == ["mapping", "transformation"]


def test_every_item_answers_the_six_provenance_questions(result):
    for i in result.items:
        assert i.source and i.source_record_id  # where it originated
        assert i.transformation_chain  # original or transformed, and which mappings
        assert i.retrieved_at  # when obtained
        assert i.authority_status  # who remains authoritative
    assert result.catalogue_version  # which catalogue version governed the plan


def test_prov_export_links_items_to_natives(result):
    prov = to_prov(result)
    assert len([k for k in prov["entity"] if k.startswith("mmfh:item/")]) == len(result.items)
    assert prov["wasDerivedFrom"]
    json.dumps(prov)  # serialisable


# -- P11: equivalence graded, not flattened ------------------------------------------
def test_egfr_equations_kept_separate_and_labelled(result):
    b = [i for i in result.items if i.source == "hospital-b" and i.concept == "concept:egfr"]
    reps = {i.represented_variable for i in b}
    assert reps == {"rv:egfr-ckdepi-2009", "rv:egfr-ckdepi-2021"}
    assert all(i.grade == Grade.narrower for i in b)
    assert any("related" in n for i in b for n in i.notes)


def test_exact_only_excludes_narrower(broker):
    r = asyncio.run(broker.handle(renal_lir(accept_grades=[Grade.exact], deadline_seconds=0.5)))
    assert not any(i.concept == "concept:egfr" for i in r.items)
    assert any(i.concept == "concept:serum-creatinine" for i in r.items)


# -- Duplicates flagged, never merged ------------------------------------------------
def test_duplicate_flagged_not_merged(result):
    dups = [i for i in result.items if "possible-duplicate" in i.flags]
    assert {i.source for i in dups} == {"hospital-b", "community"}
    assert "conflict" not in {f for i in dups for f in i.flags}
    assert any("authoritative-copy" in i.flags for i in dups if i.source == "hospital-b")


# -- Mapping lifecycle: proposed mappings are not used ----------------------------
def test_proposed_mapping_reported_as_unresolved(result):
    community = next(s for s in result.sources if s.source == "community")
    assert "iv:c-uacr" in community.unresolved_variables
    assert not any(i.source == "community" and i.concept == "concept:uacr" for i in result.items)


# -- P4: federate metadata before data ----------------------------------------------
def test_undescribed_source_is_refused(result):
    assert [e.source for e in result.excluded] == ["gp-legacy"]


# -- Identity confidence carried forward ---------------------------------------------
def test_probabilistic_links_flagged(result):
    community_items = [i for i in result.items if i.source == "community"]
    assert all("probabilistic-identity" in i.flags for i in community_items)


def test_low_confidence_link_reported_as_identity_uncertain(broker):
    r = asyncio.run(broker.handle(renal_lir(subject="NID-DEMO-0002", deadline_seconds=0.5)))
    assert status(r, "community") == SourceStatus.identity_uncertain
    assert status(r, "hospital-b") == SourceStatus.complete


# -- Window respected ----------------------------------------------------------------
def test_values_outside_window_not_returned(result):
    a_creat = [i for i in result.items if i.source == "hospital-a" and i.concept == "concept:serum-creatinine"]
    assert 90 not in [i.native_value for i in a_creat]  # 700 days ago


# -- Request validation ----------------------------------------------------------------
@pytest.mark.parametrize(
    "override",
    [{"purpose": "marketing"}, {"subject": "NID-UNKNOWN"}, {"concepts": ["concept:not-real"]}],
)
def test_invalid_requests_rejected(broker, override):
    with pytest.raises(RequestRejected):
        asyncio.run(broker.handle(renal_lir(**override)))


# -- P9: portable control plane --------------------------------------------------------
def test_cdif_export_describes_every_source():
    cat = Catalogue.load()
    doc = cat.to_cdif_jsonld()
    assert {g["@id"].split(":")[-1] for g in doc["@graph"]} == set(cat.sources)


# -- Mapping conditions are enforced ---------------------------------------------------
def test_mapping_condition_excludes_non_serum(broker):
    data = copy.deepcopy(Catalogue.load().data)
    for m in data["mappings"]:
        if m["id"] == "map:c-creatinine":
            m["condition_rule"] = {"field": "specimen", "in": ["PLASMA"]}
    b = FederationBroker(Catalogue(data), IdentityIndex.load())
    r = asyncio.run(b.handle(renal_lir(deadline_seconds=0.5)))
    community = next(s for s in r.sources if s.source == "community")
    assert "mapping condition not met" in community.detail
    assert not any(i.source == "community" and i.concept == "concept:serum-creatinine" for i in r.items)
