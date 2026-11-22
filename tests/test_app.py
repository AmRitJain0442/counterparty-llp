import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from case_fixtures import build_case
    from backend import swarm
    monkeypatch.setattr(main, "collect_live", lambda desk, *args: build_case(desk))
    monkeypatch.setattr(swarm, "draft_note", lambda *args, **kwargs: ({"note": "Offline review", "assessment": "ready", "refs": []}, "complete"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "ledger.sqlite3"))
    monkeypatch.setenv("LEDGER_BACKEND", "sqlite")
    return TestClient(main.app)


@pytest.mark.parametrize("mode", ["fixture", "replay", "synthetic"])
@pytest.mark.parametrize("route", ["/api/cases", "/api/cases/stream"])
def test_obsolete_mode_rejected_before_collection(client, monkeypatch, mode, route):
    monkeypatch.setattr(main, "collect_live", lambda *args: pytest.fail("provider invoked"))
    assert client.post(route, json={"desk": "estate", "mode": mode}).status_code == 422


def test_live_candidate_requires_consent_before_any_external_request(client, monkeypatch):
    monkeypatch.setattr(main, "collect_live", lambda *args: pytest.fail("provider invoked"))
    response = client.post("/api/cases", json={"desk": "candidate", "mode": "live", "subject": "Example"})
    assert response.status_code == 422
    assert client.get("/api/cases").json() == []


def test_stream_completes_with_persisted_case(client):
    response = client.post("/api/cases/stream", json={"desk": "estate", "subject": "Example"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert any(e["type"] == "step" for e in events)
    assert events[-1]["type"] == "case"
    case = events[-1]["case"]
    streamed = [event for event in events if event.get("agent_id")]
    assert len(streamed) == 72
    assert streamed == case["swarm_events"]
    assert client.get("/api/cases/" + case["id"]).json() == case


def test_browser_input_cannot_select_provider_calls(client):
    request = {"desk": "company", "mode": "live", "subject": "Example", "inputs": {"watch_confirmed": "true"}}
    assert client.post("/api/cases", json=request).status_code == 422


def test_parallel_creation_keeps_both_receipts(client):
    def create(_):
        return client.post("/api/cases", json={"desk": "estate", "subject": "Example"}).json()
    with ThreadPoolExecutor(max_workers=2) as workers:
        cases = list(workers.map(create, range(2)))
    assert len({case["id"] for case in cases}) == 2
    assert {case["id"] for case in client.get("/api/cases").json()} == {case["id"] for case in cases}

def test_review_keeps_original_commitment_valid(client):
    case = client.post("/api/cases", json={"desk": "payment", "subject": "Example"}).json()
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
        "subject": "Example", "evidence": [{"id":"card", "label":"Filing", "detail":"Filed on 2026-11-02.", "as_of":"2026-11-22", "source":"Registry"}],
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

    evidence = [{"id": "filing", "source": "Registry", "label": "Dated filing", "as_of": "2026-11-22",
                 "detail": "Two entities shared a name on 2026-11-02."}]
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


def test_old_cases_hidden_without_deleting_records(client):
    from backend import storage
    storage.save_case({"id": "old", "mode": "fixture"})
    assert client.get("/api/cases").json() == []
    for suffix in ("", "/receipt", "/reviews"):
        assert client.get("/api/cases/old" + suffix).status_code == 404
    assert client.post("/api/cases/old/reviews", json={"disposition": "Review complete", "note": "Done"}).status_code == 404
    assert storage._ledger().get("cases", storage._case_key("old")) is not None
    assert client.get("/api/exhibits/older-estate").status_code == 404
