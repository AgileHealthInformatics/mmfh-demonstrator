"""API smoke tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mmfh.api import app
from mmfh.scenario import renal_lir


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Logical Information Request" in r.text


def test_submit_lir_and_audit(client):
    lir = renal_lir(deadline_seconds=0.5).model_dump(mode="json")
    r = client.post("/api/lir", json=lir)
    assert r.status_code == 200
    body = r.json()
    assert body["overall_status"] == "partial"
    audit = client.get("/api/audit?limit=1").json()[0]
    assert audit["request_id"] == body["request_id"]
    # Audit holds plans and decisions, not clinical values
    assert "items" not in audit and "native_value" not in str(audit)


def test_prov_format(client):
    lir = renal_lir(deadline_seconds=0.5).model_dump(mode="json")
    body = client.post("/api/lir?format=prov", json=lir).json()
    assert "entity" in body and "wasDerivedFrom" in body


def test_rejects_unknown_purpose(client):
    lir = renal_lir(deadline_seconds=0.5).model_dump(mode="json")
    lir["purpose"] = "marketing"
    assert client.post("/api/lir", json=lir).status_code == 422


def test_cdif(client):
    r = client.get("/api/catalogue/cdif")
    assert r.headers["content-type"].startswith("application/ld+json")
    assert "@graph" in r.json()
