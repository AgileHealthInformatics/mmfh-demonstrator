# From conceptual design to code

How each element of *Metadata-Mediated Federated Health Data Architecture* is realised in this demonstrator, and what is deliberately left out.

## Reference architecture layers

| Layer | Design role | Implementation |
|---|---|---|
| 1. Sources | Persist and hold authority | `src/mmfh/sources/*` — each with its own storage and local policy |
| 2. Adapters | Contract per interface pattern | `src/mmfh/adapters/*` — `plan()` renders native queries; `execute()` returns values, provenance and the source's decision |
| 3. Identity and location | Where to ask, never what the answer is | `identity.py`, `catalogue/identity_index.json` |
| 4. Semantic and metadata control plane | Meaning and mappings | `catalogue.py`, `catalogue/catalogue.json` |
| 5. Federation broker | Plan, execute, integrate | `broker.py` |
| 6. Consumers | Presentation that surfaces gaps | `static/index.html`, `cli.py`, `api.py` |
| Cross-cutting | Policy, provenance, audit | `policy.py`, `prov.py`, `audit.py` |

## Catalogue objects

| Design object | JSON location |
|---|---|
| Sources and repositories | `sources[]` (owner, jurisdiction, authority status, lifecycle) |
| Interfaces and capability | `sources[].capability` (interface, operations, purposes accepted, latency, conformance) |
| Variables (DDI-CDI cascade) | `concepts[]` → `represented_variables[]` → `instance_variables[]` |
| Semantic bindings | `bindings` on concepts and represented variables |
| Mappings | `mappings[]` with `grade`, `lifecycle`, `conditions`/`condition_rule`, `transformation`, author, review date, version |
| Relations between representations | `representation_relations[]` (e.g. CKD-EPI 2009 *related* to 2021) |
| Transformations | `transformations[]`, each recorded as a step in the result chain |
| Quality descriptors | `sources[].quality`, inherited by each result item |
| Access conditions | `sources[].capability.purposes_accepted`; identity thresholds by purpose |

## Broker steps

| Step | Code |
|---|---|
| Validate | `FederationBroker._validate` — unknown purpose, subject or concept is rejected (HTTP 422) |
| Pre-filter policy | `policy.pre_filter` — runs before identity resolution |
| Resolve identity | `IdentityIndex.resolve` — research purposes receive only the pseudonym |
| Resolve semantics | `Catalogue.bindings_for` — approved mappings at accepted grades; proposed mappings reported as unresolved |
| Localise | Intersection of sources holding the person and sources exposing the variables |
| Plan | Adapter `plan()`, cached per catalogue version |
| Execute | `asyncio` in parallel, per-request deadline |
| Integrate | `_integrate` — conditions, rendering with native retention, identity flags, notes |
| Report | Per-source `SourceReport` and overall status |
| Audit | `audit.record` — plan, catalogue version, decisions; no values |

## Result model

Every `ResultItem` answers the six provenance questions in the design: where it originated (`source`, `source_record_id`), whether original or transformed (`flags`, `native_*` vs `rendered_*`), which mappings and transformations applied (`transformation_chain` with versions), when obtained (`retrieved_at`), which catalogue version governed the plan (`FederatedResult.catalogue_version`), and which organisation remains authoritative (`authority_status`).

## Not implemented

- Materialised purpose-specific views (openEHR, FHIR, OMOP, dimensional, feature store) and their triggers.
- Source-native preservation.
- openEHR federation as a subsystem (it would join as one more well-described source).
- Sealed routing for sensitive-service membership.
- Break-glass handling beyond carrying the declaration in the signed context.
- Real authentication, token exchange and key management.
