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
    roster = client.get(f"/api/swarms/{desk}").json()["agents"]
    assert case["swarm_roster"] == roster
    assert {a["id"] for a in roster} == {r["agent_id"] for r in case["swarm_reports"]}
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


@pytest.mark.parametrize("assessment,expected", [("ready", "FORECAST FOR REVIEW"), ("needs_evidence", "PARTNER REVIEW")])
def test_live_challenge_can_refer_a_proposed_finding(client, monkeypatch, assessment, expected):
    from backend import swarm
    monkeypatch.setattr(main, "collect_live", lambda *args: {
        "subject": "Example", "evidence": [{"id":"card", "label":"Filing", "detail":"Dated filing", "source":"Registry"}],
        "steps": [], "flows": [], "credits": 0,
    })
    monkeypatch.setattr(main, "adjudicate", lambda *a: {"verdict":"FORECAST FOR REVIEW", "summary":"Reviewable finding"})
    def review(desk, evidence, verdict, role, **assignment):
        choice = assessment if role == "counsel" else "ready"
        return {"note": "Check the dated filing.", "assessment": choice, "refs": ["card"]}, "complete"
    monkeypatch.setattr(swarm, "draft_note", review)
    response = client.post("/api/cases", json={"desk":"company", "subject":"Example", "mode":"live"})
    assert response.status_code == 201
    case = response.json()
    assert case["verdict"] == expected
    referrals = case["council_decision"]["referred_by"]
    assert referrals == (["Scope challenger", "Timing challenger"] if assessment == "needs_evidence" else [])
    assert client.get("/api/cases/" + case["id"] + "/receipt").status_code == 200


def test_specialist_concern_reaches_the_filed_decision(client, monkeypatch):
    from backend import swarm

    evidence = [{"id": "filing", "source": "Registry", "label": "Dated filing", "detail": "Two entities share a name."}]
    monkeypatch.setattr(main, "collect_live", lambda *args: dict(evidence=evidence, steps=[], flows=[], credits=0))
    monkeypatch.setattr(main, "adjudicate", lambda *args: dict(verdict="FORECAST FOR REVIEW", summary="Proposed forecast"))
    specialist = next(a for a in swarm.agents_for("company") if a["parent_id"] == "identity")

    def review(desk, evidence, verdict, role, *, persona, mandate):
        assessment = "needs_evidence" if persona == specialist["persona"] else "ready"
        return {"note": "Compare issuer registration numbers.", "assessment": assessment, "refs": ["filing"]}, "complete"

    monkeypatch.setattr(swarm, "draft_note", review)
    case = client.post("/api/cases", json={"desk": "company", "subject": "Example", "mode": "live"}).json()
    assert case["verdict"] == "PARTNER REVIEW"
    decision = case["council_decision"]
    assert decision["specialist_referrals"] == [specialist["id"]]
    assert "Identity resolver" in decision["referred_by"]
    assert client.get("/api/cases/" + case["id"] + "/receipt").json()["digest"] == case["receipt"]
