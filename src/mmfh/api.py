"""HTTP API and demo UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from . import __version__, audit
from .broker import FederationBroker, RequestRejected
from .catalogue import Catalogue
from .identity import IdentityIndex
from .models import FederatedResult, LogicalInformationRequest
from .prov import to_prov
from .scenario import renal_lir

STATIC = Path(__file__).parent / "static"

catalogue = Catalogue.load(os.environ.get("MMFH_CATALOGUE") or None)
index = IdentityIndex.load(os.environ.get("MMFH_IDENTITY_INDEX") or None)
broker = FederationBroker(catalogue, index)

app = FastAPI(
    title="Metadata-Mediated Federated Health — demonstrator",
    version=__version__,
    description=(
        "A runnable illustration of a metadata-mediated federation: a governed control plane "
        "(catalogue, semantics, identity, policy, provenance) over distributed sources. "
        "All data is synthetic."
    ),
)


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health", tags=["service"])
def health() -> dict:
    return {"status": "ok", "version": __version__, "catalogue_version": catalogue.version}


@app.get("/api/catalogue", tags=["control plane"])
def get_catalogue() -> dict:
    """The full control-plane catalogue (sources, variable cascade, mappings, transformations)."""
    return catalogue.data


@app.get("/api/catalogue/cdif", tags=["control plane"])
def get_cdif() -> JSONResponse:
    """Portable CDIF-style JSON-LD export of source and variable descriptions (P9)."""
    return JSONResponse(catalogue.to_cdif_jsonld(), media_type="application/ld+json")


@app.get("/api/persons", tags=["control plane"])
def persons() -> list[dict]:
    """Synthetic subjects available in the identity index (display names only)."""
    return index.persons()


@app.get("/api/scenario/renal", tags=["requests"], response_model=LogicalInformationRequest)
def renal_scenario() -> LogicalInformationRequest:
    """The worked renal-function scenario as a Logical Information Request."""
    return renal_lir()


@app.post("/api/lir", tags=["requests"], response_model=None)
async def submit_lir(
    lir: LogicalInformationRequest, format: Literal["result", "prov"] = Query("result")
) -> FederatedResult | dict:
    """Submit a Logical Information Request to the Federation Broker."""
    try:
        result = await broker.handle(lir)
    except RequestRejected as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return to_prov(result) if format == "prov" else result


@app.get("/api/audit", tags=["service"])
def get_audit(limit: int = 20) -> list[dict]:
    """Broker-side audit: plans and source decisions, no clinical values."""
    return audit.recent(limit)
