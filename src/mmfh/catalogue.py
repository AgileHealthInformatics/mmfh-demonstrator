"""Metadata catalogue: the persistent store of the control plane.

Holds sources and capabilities, the DDI-CDI style variable cascade
(concept -> represented variable -> instance variable), mapping assertions
with equivalence grades, and transformations. The broker plans against a
specific catalogue version, which is recorded in every result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .models import Grade

DEFAULT_CATALOGUE = Path(__file__).resolve().parents[2] / "catalogue" / "catalogue.json"


@dataclass(frozen=True)
class VariableBinding:
    """An approved route from a requested concept to one source's instance variable."""

    instance_variable: dict[str, Any]
    represented_variable: dict[str, Any]
    mapping: dict[str, Any]
    grade: Grade


class Catalogue:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.version: str = data["catalogue_version"]
        self.concepts = {c["id"]: c for c in data["concepts"]}
        self.represented = {r["id"]: r for r in data["represented_variables"]}
        self.sources = {s["id"]: s for s in data["sources"]}
        self.instance_vars = {v["id"]: v for v in data["instance_variables"]}
        self.mappings = list(data["mappings"])
        self.transformations = {t["id"]: t for t in data.get("transformations", [])}
        self.relations = list(data.get("representation_relations", []))
        self.purposes: list[str] = data["purposes"]
        self.identity_thresholds: dict[str, float] = data["identity_thresholds"]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Catalogue":
        p = Path(path) if path else DEFAULT_CATALOGUE
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # -- P4: federate metadata before data --------------------------------
    def is_registered(self, source_id: str) -> bool:
        return source_id in self.sources

    # -- Semantic resolution ----------------------------------------------
    def bindings_for(
        self, concept_id: str, source_id: str, accept: set[Grade]
    ) -> tuple[list[VariableBinding], list[str]]:
        """Return approved bindings for concept at source, and ids of unresolved variables.

        Unresolved = the source exposes an instance variable for this concept
        but no *approved* mapping exists (e.g. still 'proposed').
        Variables whose grade falls outside the consumer's accepted grades are
        silently out of scope (the consumer asked not to receive them).
        """
        bound: list[VariableBinding] = []
        unresolved: list[str] = []
        for m in self.mappings:
            if m["to_concept"] != concept_id:
                continue
            iv = self.instance_vars.get(m["from"])
            if iv is None or iv["source"] != source_id:
                continue
            grade = Grade(m["grade"])
            if m.get("lifecycle") != "approved":
                unresolved.append(iv["id"])
                continue
            if grade not in accept:
                continue
            rv = self.represented[iv["represented_variable"]]
            bound.append(VariableBinding(iv, rv, m, grade))
        return bound, unresolved

    def exposes_concept(self, concept_id: str, source_id: str) -> bool:
        for m in self.mappings:
            iv = self.instance_vars.get(m["from"])
            if iv and iv["source"] == source_id and m["to_concept"] == concept_id:
                return True
        return False

    def preferred_unit(self, concept_id: str) -> Optional[str]:
        """The unit a consumer gets when asking for rendering: the first exact
        represented variable for the concept. A purpose-specific choice, not a
        canonical persistence model."""
        for rv in self.represented.values():
            if rv["concept"] == concept_id and rv.get("unit"):
                return rv["unit"]
        return None

    def related_notes(self, rv_id: str) -> list[str]:
        notes = []
        for r in self.relations:
            if rv_id in (r["a"], r["b"]):
                other = r["b"] if r["a"] == rv_id else r["a"]
                notes.append(
                    f"{self.represented[rv_id]['label']} is '{r['grade']}' to "
                    f"{self.represented[other]['label']}: {r.get('note', '')}".strip()
                )
        return notes

    # -- P9: portable metadata (CDIF-style JSON-LD export) ------------------
    def to_cdif_jsonld(self) -> dict[str, Any]:
        graph = []
        for s in self.sources.values():
            ivs = [v for v in self.instance_vars.values() if v["source"] == s["id"]]
            graph.append(
                {
                    "@id": f"urn:mmfh:source:{s['id']}",
                    "@type": ["schema:Dataset", "dcat:Dataset"],
                    "schema:name": s["label"],
                    "schema:publisher": {"@type": "schema:Organization", "schema:name": s["owner"]},
                    "schema:version": self.version,
                    "dcat:accessService": {
                        "@type": "dcat:DataService",
                        "dcterms:conformsTo": s["capability"]["interface"],
                    },
                    "schema:conditionsOfAccess": "Purposes accepted: "
                    + ", ".join(s["capability"]["purposes_accepted"]),
                    "schema:variableMeasured": [
                        {
                            "@type": ["schema:PropertyValue", "cdi:InstanceVariable"],
                            "@id": f"urn:mmfh:{v['id']}",
                            "schema:name": self.represented[v["represented_variable"]]["label"],
                            "cdi:takesSubstantiveValuesFrom": self.represented[v["represented_variable"]].get("unit"),
                            "cdi:basedOn": f"urn:mmfh:{v['represented_variable']}",
                        }
                        for v in ivs
                    ],
                }
            )
        return {
            "@context": {
                "schema": "https://schema.org/",
                "dcat": "http://www.w3.org/ns/dcat#",
                "dcterms": "http://purl.org/dc/terms/",
                "cdi": "http://ddialliance.org/Specification/DDI-CDI/1.0/RDF/",
            },
            "@graph": graph,
        }
