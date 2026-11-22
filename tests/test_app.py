import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "ledger.sqlite3"))
    monkeypatch.setenv("LEDGER_BACKEND", "sqlite")
    return TestClient(main.app)


@pytest.mark.parametrize("desk", ["payment", "candidate", "estate", "company"])
def test_demo_filed_and_retrievable(client, desk):
    response = client.post("/api/cases", json={"mode": "demo", "desk": desk})
    assert response.status_code == 201, response.text
    case = response.json()
    assert case["mode"] == "demo"
    assert case["evidence"] and case["verdict"] and case["receipt"]
    assert client.get("/api/cases/" + case["id"]).json() == case
    assert client.get("/api/cases").json() == [case]


def test_live_candidate_requires_consent_before_any_external_request(client, monkeypatch):
    monkeypatch.setattr(main, "collect_live", lambda *args: pytest.fail("provider invoked"))
    response = client.post("/api/cases", json={"desk": "candidate", "mode": "live", "subject": "Example"})
    assert response.status_code == 422
    assert client.get("/api/cases").json() == []


def test_stream_completes_with_persisted_case(client):
    response = client.post("/api/cases/stream", json={"desk": "estate", "mode": "demo"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert any(e["type"] == "step" for e in events)
    assert events[-1]["type"] == "case"
    case = events[-1]["case"]
    assert client.get("/api/cases/" + case["id"]).json() == case


def test_browser_input_cannot_select_provider_calls(client):
    request = {"desk": "company", "mode": "live", "subject": "Demo", "inputs": {"watch_confirmed": "true"}}
    assert client.post("/api/cases", json=request).status_code == 422


def test_parallel_creation_keeps_both_receipts(client):
    def create(_):
        return client.post("/api/cases", json={"desk": "estate", "mode": "demo"}).json()
    with ThreadPoolExecutor(max_workers=2) as workers:
        cases = list(workers.map(create, range(2)))
    assert len({case["id"] for case in cases}) == 2
    assert {case["id"] for case in client.get("/api/cases").json()} == {case["id"] for case in cases}

def test_review_keeps_original_commitment_valid(client):
    case = client.post("/api/cases", json={"desk": "payment", "mode": "demo"}).json()
    url = "/api/cases/" + case["id"]
    entry = {"disposition": "Callback requested", "note": "Reviewer requested a call using the number on file."}
    response = client.post(url + "/reviews", json=entry)
    assert response.status_code == 201
    assert client.get(url + "/reviews").json() == [response.json()]
    assert client.get(url + "/receipt").json()["digest"] == case["receipt"]
