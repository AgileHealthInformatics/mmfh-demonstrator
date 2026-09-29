"""Adapters: one per interface pattern, so onboarding a new source of a known
pattern is configuration (a catalogue entry), not code.

Each adapter translates a planned sub-request into the source's native
interface, preserves native values and identifiers, returns the source's
access decision, and reports failures explicitly - never as empty results.
"""

from .base import Adapter, AdapterResponse, RawRecord, SubRequest
from .dataset import DatasetAdapter
from .dicomweb import DicomWebReportsAdapter
from .fhir import FhirSearchAdapter
from .openehr import OpenEhrAqlAdapter
from .sql import SqlServiceAdapter

REGISTRY: dict[str, Adapter] = {
    "openehr-aql": OpenEhrAqlAdapter(),
    "fhir-r4-search": FhirSearchAdapter(),
    "sql-service": SqlServiceAdapter(),
    "dicomweb-reports": DicomWebReportsAdapter(),
    "dataset-api": DatasetAdapter(),
}

__all__ = ["Adapter", "AdapterResponse", "RawRecord", "SubRequest", "REGISTRY"]
