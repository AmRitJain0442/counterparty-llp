"""Counterparty LLP single-origin application."""
import os
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .account import capabilities
from .adjudication import adjudicate
from .demo import build_demo
from .swarm import agents_for, run_council
from .receipts import ReceiptError, create_receipt, verify_receipt
from .watch import router as watch_router
from .watch_history import watch_history
from . import progress
from .live import collect_live
from .storage import append_review, get_case, list_cases, reviews_for, save_case

app = FastAPI(title="Counterparty LLP", version="0.1.0")
app.include_router(watch_router)
WEB = Path(__file__).resolve().parents[1] / "web" / "dist"


class Intake(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desk: Literal["payment", "candidate", "estate", "company"]
    mode: Literal["demo", "live"]
    subject: str = Field(default="", max_length=180)
    consent: bool = False
    inputs: dict[str, str] = Field(default_factory=dict, max_length=14)

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, inputs):
        allowed = {"domain", "sender_domain", "person_url", "ifsc", "orgnr", "cik", "claim", "lei"}
        if inputs.keys() - allowed:
            raise ValueError("Unrecognized desk input")
        if any(len(v) > (2000 if k == "claim" else 300) for k, v in inputs.items()):
            raise ValueError("Desk input exceeds its length limit")
        return {k: v.strip() for k, v in inputs.items() if v.strip()}


@app.middleware("http")
async def same_origin(request: Request, call_next):
    # The ledger and paid collection routes share the authenticated service origin.
    if request.method == "POST" and request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "Use the application origin"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/exhibits/older-estate")
def historical_estate():
    file = Path(__file__).parent / "exhibits" / "older-estate.json"
    return json.loads(file.read_text(encoding="utf-8"))


@app.get("/api/watch")
def company_watch():
    return watch_history()


@app.get("/api/capabilities")
def provider_capabilities():
    return capabilities()


@app.get("/api/swarms/{desk}")
def roster(desk: Literal["payment", "candidate", "estate", "company"]):
    return {"desk": desk, "agents": agents_for(desk)}


@app.get("/api/cases")
def cases():
    return list_cases()


@app.get("/api/cases/{case_id}")
def detail(case_id: str):
    case = get_case(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


class ReviewerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    disposition: Literal["Callback requested", "Clarification requested", "Evidence corrected", "Review complete"]
    note: str = Field(min_length=1, max_length=800)


@app.get("/api/cases/{case_id}/reviews")
def case_reviews(case_id: str):
    detail(case_id)
    return reviews_for(case_id)


@app.post("/api/cases/{case_id}/reviews", status_code=201)
def add_case_review(case_id: str, entry: ReviewerEntry):
    review = {**entry.model_dump(), "id": uuid4().hex, "as_of": datetime.now(timezone.utc).isoformat()}
    try:
        return append_review(case_id, review)
    except KeyError:
        raise HTTPException(404, "Case not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/cases/{case_id}/receipt")
def check_receipt(case_id: str):
    case = detail(case_id)
    try:
        status = verify_receipt(case, case.get("receipt_record"))
    except ReceiptError as exc:
        raise HTTPException(409, "Receipt could not be verified") from exc
    return {"id": case_id, "digest": case["receipt"], "status": status}


@app.post("/api/cases", status_code=201)
def investigate(intake: Intake):
    subject = intake.subject.strip()
    if intake.mode == "live" and not subject:
        raise HTTPException(422, "Enter a subject for this live inquiry")
    if intake.mode == "live" and intake.desk == "candidate" and not intake.consent:
        raise HTTPException(422, "Candidate consent is required")
    if intake.mode == "live":
        with progress.record_collection() as collections:
            raw = collect_live(intake.desk, subject, intake.consent, intake.inputs)
    else:
        raw = build_demo(intake.desk)
        collections = []
    progress.report("Opposing counsel", "running", "Checking evidence and alternative explanations")
    ruling = adjudicate(intake.desk, raw)
    case = {
        "id": uuid4().hex,
        "desk": intake.desk,
        "subject": raw.get("subject") or subject,
        "mode": intake.mode,
        "as_of": raw.get("as_of") or datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verdict": ruling["verdict"],
        "summary": ruling["summary"],
        "evidence": raw["evidence"],
        "steps": raw["steps"],
        "flows": raw["flows"],
        "credits": raw["credits"],
    }
    for index, row in enumerate(case["evidence"], start=1):
        row.setdefault("id", f"source-card-{index}")
    trace = []
    stream_event = progress.current_sink()

    def observe(item):
        event = {"type": "step", "at": datetime.now(timezone.utc).isoformat(), **item}
        trace.append(event)
        if stream_event:
            stream_event(event)

    reports = run_council(intake.desk, case["evidence"], ruling["verdict"], observe, intake.mode)
    case["collection_events"] = collections
    case["swarm_roster"] = agents_for(intake.desk)
    case["swarm_events"] = trace
    case["swarm_reports"] = reports
    leads = [report for report in reports if not report.get("parent_id")]
    case["steps"].extend({k: report[k] for k in ("name", "status", "detail")} for report in leads)
    by_id = {r["agent_id"]: r for r in reports}
    if intake.mode == "live":
        case["reviews"] = {"analyst": by_id["analyst_scope"], "counsel": by_id["challenger_scope"]}
        partner = by_id["partner"]
        if partner["status"] == "complete":
            case["draft"] = partner["detail"]
        flagged = [r for r in reports if r.get("assessment") == "needs_evidence" or r["status"] != "complete"]
        case["council_decision"] = {
            "proposed_verdict": ruling["verdict"],
            "referred_by": [r["name"] for r in flagged if not r.get("parent_id")],
            "specialist_referrals": [r["agent_id"] for r in flagged if r.get("parent_id")],
            "disposition": "further review" if flagged else "review complete",
        }
        if flagged and ruling["verdict"] in {"HELD", "FORECAST FOR REVIEW", "REQUEST FOR EXPLANATION", "FAILED", "KILLED"}:
            case["verdict"] = "PARTNER REVIEW"
            case["summary"] = "The council referred the proposed finding for further evidence. Review the flagged agent reports before acting."
    progress.report("Ledger", "running", "Committing the evidence receipt")
    if raw.get("forecast"):
        case["forecast"] = raw["forecast"]
    if intake.mode == "live" and case["verdict"] == "FORECAST FOR REVIEW" and os.getenv("REKOR_ENABLED") == "1":
        signed = {**case, "verdict": "SIGNED"}
        try:
            receipt = create_receipt(signed, publish=True)
            case = signed
        except ReceiptError:
            case["steps"].append({"name":"Partner signing", "status":"unavailable",
                                  "detail":"Public timestamp verification is pending."})
            receipt = create_receipt(case)
    else:
        receipt = create_receipt(case)
    case["receipt_record"] = receipt
    case["receipt"] = receipt["digest"]
    save_case(case)
    return case


@app.post("/api/cases/stream")
async def stream_investigation(intake: Intake):
    """Stream actual collection boundaries and the same persisted case as POST /cases."""
    loop = asyncio.get_running_loop()
    events = asyncio.Queue()

    def send(event):
        loop.call_soon_threadsafe(events.put_nowait, event)

    def run():
        token = progress.attach(send)
        try:
            send({"type": "case", "case": investigate(intake)})
        except HTTPException as exc:
            send({"type": "error", "detail": exc.detail})
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Desk investigation interrupted")
            send({"type": "error", "detail": "Investigation interrupted before filing."})
        finally:
            progress.detach(token)

    async def body():
        task = asyncio.create_task(asyncio.to_thread(run))
        try:
            while True:
                event = await events.get()
                yield json.dumps(event) + "\n"
                if event["type"] in {"case", "error"}:
                    break
        finally:
            await asyncio.shield(task)

    return StreamingResponse(body(), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no"})


if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "Unknown API route")
    file = (WEB / path).resolve()
    if WEB in file.parents and file.is_file():
        return FileResponse(file)
    if not (WEB / "index.html").exists():
        raise HTTPException(503, "Build the frontend with npm ci and npm run build in web/")
    return FileResponse(WEB / "index.html")
