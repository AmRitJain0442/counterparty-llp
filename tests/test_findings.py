import json

import pytest

from backend.findings import interpret


AS_OF = "2026-10-15T11:00:00+00:00"
PRIVATE = "PRIVATE-DO-NOT-PUBLISH"
PROFILE = "https://www.linkedin.com/in/private-person/"
INPUTS = {"domain": "vendor.example", "cik": "42", "person_url": PROFILE}


def row(op, data, *, provider="crustdata", status="ok", as_of=AS_OF):
    # Parallel provider lanes can each start at e1.
    return dict(id="e1", provider=provider, operation=op, status=status, as_of=as_of,
                data=data, source="https://example.invalid/" + PRIVATE)


def run(desk, *rows, inputs=None, subject="Vendor Inc.", signals=()):
    raw = dict(evidence=list(rows), steps=[{k: r[k] for k in ("operation", "provider", "status")} for r in rows],
               credits=[], flows=[], signals=list(signals))
    return interpret(desk, subject, INPUTS if inputs is None else inputs, raw)


def company(op="company_identify", *, cid=21, domain="vendor.example", **extra):
    data = {"crustdata_company_id": cid, "basic_info": {"name": "Vendor", "primary_domain": domain}, **extra}
    kind, value = ("domain", domain) if op == "company_identify" else ("crustdata_company_id", str(cid))
    return row(op, [{"matched_on": value, "match_type": kind,
                     "matches": [{"confidence_score": 1.0, "company_data": data}]}])


def submissions(**overrides):
    return row("submissions", {
        "name": "VENDOR, INC.", "cik": "0000000042", "tickers": ["VEND"],
        "filings": {"recent": {
            "form": ["10-K", "8-K", "8-K", "8-K/A", "8-K", "8-K", "8-K"],
            "filingDate": ["2026-10-12", "2026-07-03", "2026-10-05", "2026-09-16",
                           "2026-10-20", "2026-10-15", "bogus"],
            "reportDate": ["", "2026-07-01", "2026-10-01", "2026-09-10", "", "", ""],
            "items": ["5.02", "5.02,4.01", "2.02,5.02,9.01", "4.01", "4.01", "15.02,4.010", "4.01"],
            "accessionNumber": ["", "", "0000000042-26-000003", "", "", "", ""],
        }}, **overrides,
    }, provider="sec")


def card(result, label):
    return next(e for e in result["evidence"] if e["label"] == label)


def test_sec_latest_filing_per_exact_item_retains_column_alignment_and_report_date():
    result = run("company", company(), submissions())
    officer = card(result, "8-K Item 5.02")
    auditor = card(result, "8-K Item 4.01")
    assert (officer["observed_on"], auditor["observed_on"]) == ("2026-10-05", "2026-09-16")
    assert "2026-10-01" in officer["detail"] and "2026-09-10" in auditor["detail"]
    assert officer["as_of"] == auditor["as_of"] == AS_OF
    assert officer["url"].endswith("/42/000000004226000003/0000000042-26-000003-index.htm")
    assert "8-K/A" in auditor["detail"]
    assert len({e["id"] for e in result["evidence"]}) == len(result["evidence"])
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("overrides", [{"cik": "43"}, {"name": "Vendor Subsidiary LLC"}, {"cik": None}])
def test_incompatible_issuer_identity_withholds_its_observations(overrides):
    result = run("company", company(), submissions(**overrides))
    assert all(e["source"] != "sec" for e in result["evidence"])
    assert any(s["name"] == "SEC issuer identity" and s["status"] == "unresolved" for s in result["steps"])


def test_independently_identified_sec_observation_survives_other_lane_failure():
    result = run("company", row("company_identify", None, status="rate_limited"),
                 submissions(), inputs={"cik": "42"}, subject="VEND")
    assert card(result, "8-K Item 4.01")["source"] == "sec"
    assert any(s["status"] == "rate_limited" for s in result["steps"])


@pytest.mark.parametrize("data", [None, [], {}, {"filings": None}, {"filings": {"recent": {"form": ["8-K"]}}}])
def test_partial_submissions_never_generate_an_event_from_retrieval_time(data):
    bad = submissions()
    bad["data"].update(data if isinstance(data, dict) else {"filings": data})
    if data == {}:
        bad["data"]["filings"] = {}
    result = run("company", company(), bad)
    assert all(e["source"] != "sec" for e in result["evidence"])
