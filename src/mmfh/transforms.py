"""Transformations applied under approved mappings.

Only transformations registered in the catalogue may run, and each run is
recorded in the item's transformation chain (P6).
"""

from __future__ import annotations

from typing import Any, Optional


def apply(transform: dict[str, Any], value: Any) -> Any:
    factor = transform.get("factor")
    if factor is None:
        raise ValueError(f"Unsupported transformation {transform['id']}")
    return round(float(value) * float(factor), 1)


def unit_conversion_for(transformations: dict[str, dict], from_unit: Optional[str], to_unit: Optional[str]) -> Optional[dict]:
    if not from_unit or not to_unit or from_unit == to_unit:
        return None
    for t in transformations.values():
        if t.get("from_unit") == from_unit and t.get("to_unit") == to_unit:
            return t
    return None
