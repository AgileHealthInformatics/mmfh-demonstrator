"""Longitudinal identity and location index.

Tells the broker *where to ask*, never *what the answer is*. Holds membership
and local identifiers only, with match method and confidence carried forward.
Research repositories are reached only through a pseudonym issued by a trusted
linkage service, never through the clinical identifier.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_INDEX = Path(__file__).resolve().parents[2] / "catalogue" / "identity_index.json"


@dataclass(frozen=True)
class IdentityLink:
    source: str
    local_id: str
    method: str
    confidence: float


class IdentityIndex:
    def __init__(self, data: dict[str, Any]):
        self._persons = {p["person_id"]: p for p in data["persons"]}

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "IdentityIndex":
        p = Path(path) if path else DEFAULT_INDEX
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def known(self, person_id: str) -> bool:
        return person_id in self._persons

    def display(self, person_id: str) -> str:
        return self._persons.get(person_id, {}).get("display", person_id)

    def persons(self) -> list[dict[str, str]]:
        return [{"person_id": k, "display": v.get("display", k)} for k, v in self._persons.items()]

    def resolve(self, person_id: str, purpose: str) -> list[IdentityLink]:
        person = self._persons.get(person_id)
        if not person:
            return []
        if purpose == "research":
            ps = person.get("research_pseudonym")
            if not ps:
                return []
            return [IdentityLink(ps["source"], ps["local_id"], "pseudonymous-linkage", 1.0)]
        return [
            IdentityLink(lk["source"], lk["local_id"], lk["method"], float(lk["confidence"]))
            for lk in person.get("links", [])
        ]
