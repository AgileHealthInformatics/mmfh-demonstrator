"""Data contracts: the Logical Information Request and the federated result model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Equivalence grades (P11). Ordered from strongest to weakest.
# --------------------------------------------------------------------------
class Grade(str, Enum):
    exact = "exact"
    narrower = "narrower"
    broader = "broader"
    related = "related"
    unmappable = "unmappable"


# --------------------------------------------------------------------------
# Logical Information Request (LIR)
# Declarative: no joins, no arbitrary predicates, no source names.
# --------------------------------------------------------------------------
class Requester(BaseModel):
    id: str = Field(..., description="Authenticated identity of the requester")
    role: str = Field(..., description="Role, e.g. 'consultant-nephrologist'")
    organisation: str


class TimeWindow(BaseModel):
    effective_from: datetime
    effective_to: Optional[datetime] = None
    apply_to_recorded_time: bool = False


class LogicalInformationRequest(BaseModel):
    subject: str = Field(..., description="Governed person identifier, e.g. NID-DEMO-0001")
    concepts: list[str] = Field(..., min_length=1, description="Concept ids from the catalogue")
    window: TimeWindow
    context: dict[str, str] = Field(default_factory=dict, description="Context qualifiers")
    accept_grades: list[Grade] = Field(
        default_factory=lambda: [Grade.exact],
        description="Equivalence grades the consumer accepts. Default exact only.",
    )
    render_units: bool = Field(False, description="Render values into the concept's preferred unit (UCUM)")
    purpose: str = Field(..., description="Purpose of use from the controlled list")
    requester: Requester
    provenance_depth: Literal["summary", "full"] = "full"
    deadline_seconds: float = Field(8.0, gt=0, le=60, description="Return within deadline with partial status")
    break_glass: bool = False


# --------------------------------------------------------------------------
# Result model
# --------------------------------------------------------------------------
class SourceStatus(str, Enum):
    complete = "complete"
    no_matching_data = "no_matching_data"
    partial = "partial"
    not_permitted = "not_permitted"
    unavailable = "unavailable"
    failed = "failed"
    semantics_unresolved = "semantics_unresolved"
    identity_uncertain = "identity_uncertain"
    not_asked = "not_asked"


class TransformStep(BaseModel):
    kind: Literal["mapping", "transformation"]
    id: str
    version: str
    detail: str


class ResultItem(BaseModel):
    item_id: str
    concept: str
    concept_label: str
    grade: Grade
    represented_variable: str
    represented_label: str
    native_value: Any
    native_unit: Optional[str]
    native_representation: dict[str, Any]
    rendered_value: Optional[Any] = None
    rendered_unit: Optional[str] = None
    subject: str
    match_method: str
    match_confidence: float
    effective_time: datetime
    recorded_time: Optional[datetime] = None
    source: str
    source_record_id: str
    authority_status: str
    transformation_chain: list[TransformStep]
    quality: list[str] = Field(default_factory=list)
    retrieved_at: datetime
    flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SourceReport(BaseModel):
    source: str
    label: str
    interface: Optional[str] = None
    status: SourceStatus
    items_returned: int = 0
    detail: str = ""
    native_queries: list[str] = Field(default_factory=list)
    unresolved_variables: list[str] = Field(default_factory=list)
    elapsed_ms: Optional[int] = None


class ExcludedSource(BaseModel):
    source: str
    reason: str


class FederatedResult(BaseModel):
    request_id: str
    catalogue_version: str
    purpose: str
    subject: str
    overall_status: Literal["complete", "partial"]
    items: list[ResultItem]
    sources: list[SourceReport]
    excluded: list[ExcludedSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
