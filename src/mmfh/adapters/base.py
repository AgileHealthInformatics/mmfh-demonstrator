"""Adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..catalogue import VariableBinding


@dataclass
class SubRequest:
    source_id: str
    local_id: str
    bindings: list[VariableBinding]
    effective_from: datetime
    effective_to: datetime
    context: dict[str, Any]  # signed request context


@dataclass
class RawRecord:
    instance_variable: str
    value: Any
    unit: Optional[str]
    effective: datetime
    recorded: Optional[datetime]
    record_id: str
    accession: Optional[str] = None
    native: dict[str, Any] = field(default_factory=dict)
    specimen: Optional[str] = None


@dataclass
class AdapterResponse:
    records: list[RawRecord]
    withheld: int
    decision: str
    native_queries: list[str]
    detail: str = ""


class Adapter(ABC):
    interface: str

    @abstractmethod
    def plan(self, sub: SubRequest) -> list[str]:
        """Render the native query text(s) for review and audit."""

    @abstractmethod
    async def execute(self, sub: SubRequest) -> AdapterResponse:
        """Execute against the source's governed interface."""
