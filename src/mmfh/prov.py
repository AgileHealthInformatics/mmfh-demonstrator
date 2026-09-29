"""W3C PROV export of a federated result (PROV-JSON shape).

Entities are values, activities are retrieval / mapping / transformation /
integration, agents are sources, adapters, the broker and mapping authors.
"""

from __future__ import annotations

from typing import Any

from .models import FederatedResult


def to_prov(result: FederatedResult) -> dict[str, Any]:
    entity: dict[str, Any] = {}
    activity: dict[str, Any] = {}
    agent: dict[str, Any] = {"mmfh:broker": {"prov:type": "prov:SoftwareAgent", "mmfh:catalogueVersion": result.catalogue_version}}
    was_generated_by: dict[str, Any] = {}
    was_derived_from: dict[str, Any] = {}
    was_associated_with: dict[str, Any] = {}

    for s in result.sources:
        agent[f"mmfh:source/{s.source}"] = {"prov:type": "prov:Organization", "prov:label": s.label}
        if s.interface:
            agent[f"mmfh:adapter/{s.interface}"] = {"prov:type": "prov:SoftwareAgent"}

    for it in result.items:
        native = f"mmfh:native/{it.item_id}"
        integrated = f"mmfh:item/{it.item_id}"
        retrieval = f"mmfh:retrieval/{result.request_id}/{it.source}"
        entity[native] = {"prov:value": it.native_value, "mmfh:unit": it.native_unit, "mmfh:sourceRecord": it.source_record_id}
        entity[integrated] = {
            "prov:value": it.rendered_value if it.rendered_value is not None else it.native_value,
            "mmfh:unit": it.rendered_unit or it.native_unit,
            "mmfh:concept": it.concept,
            "mmfh:grade": it.grade.value,
        }
        activity.setdefault(retrieval, {"prov:type": "mmfh:Retrieval", "prov:endTime": it.retrieved_at.isoformat()})
        was_associated_with[f"_:assoc-{it.item_id}"] = {"prov:activity": retrieval, "prov:agent": f"mmfh:source/{it.source}"}
        was_generated_by[f"_:gen-{it.item_id}"] = {"prov:entity": native, "prov:activity": retrieval}
        prev = native
        for n, step in enumerate(it.transformation_chain):
            act = f"mmfh:{step.kind}/{step.id}@{step.version}"
            activity.setdefault(act, {"prov:type": f"mmfh:{step.kind.title()}", "prov:label": step.detail})
            nxt = integrated if n == len(it.transformation_chain) - 1 else f"mmfh:intermediate/{it.item_id}/{n}"
            if nxt != integrated:
                entity[nxt] = {}
            was_derived_from[f"_:der-{it.item_id}-{n}"] = {"prov:generatedEntity": nxt, "prov:usedEntity": prev, "prov:activity": act}
            prev = nxt

    return {
        "prefix": {"prov": "http://www.w3.org/ns/prov#", "mmfh": "urn:mmfh:"},
        "entity": entity,
        "activity": activity,
        "agent": agent,
        "wasGeneratedBy": was_generated_by,
        "wasDerivedFrom": was_derived_from,
        "wasAssociatedWith": was_associated_with,
    }
