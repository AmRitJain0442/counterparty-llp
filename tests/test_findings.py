import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.findings import interpret
from backend import providers


AS_OF = "2026-10-15T11:00:00+00:00"
PRIVATE = "PRIVATE-DO-NOT-PUBLISH"
PROFILE = "https://www.linkedin.com/in/private-person/"
INPUTS = {"domain": "vendor.example", "cik": "42", "person_url": PROFILE}


@pytest.fixture
def adjudicate():
    from backend.adjudication import adjudicate
    return adjudicate


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


@pytest.mark.parametrize("overrides", [
    {"cik": "43"}, {"name": "Vendor Subsidiary LLC"}, {"website": "https://unrelated.example/"}, {"cik": None},
])
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


def role(cid, start, end=None):
    return {"crustdata_company_id": cid, "start_date": start, "end_date": end, "title": PRIVATE}


def profile(pid, past, current=(), updated="2026-10-12"):
    return {"crustdata_person_id": pid, "updated_at": updated, "basic_profile": {"name": PRIVATE},
            "experience": {"employment_details": {"past": list(past), "current": list(current)}}}


def person(data, *, url=PROFILE, confidence=1):
    return row("person_enrich", [{"matched_on": url, "match_status": "matched",
                                  "match_type": "professional_network_profile_url",
                                  "matches": [{"confidence_score": confidence, "person_data": data}]}])


def rdap(domain="vendor-billing.example", registered="2026-10-04"):
    return row("rdap", {"objectClassName": "domain", "ldhName": domain,
                        "events": [{"eventAction": "last changed", "eventDate": "2026-10-13"},
                                   {"eventAction": "registration", "eventDate": registered}],
                        "entities": [PRIVATE]}, provider="rdap")


PAY = {**INPUTS, "sender_domain": "vendor-billing.example", "ifsc": "ABCD0123456"}
VENDOR = role(21, "2020-01-01", "2026-07-11")
NEXT = role(71, "2026-08-08")


def test_payment_uses_first_subsequent_start_and_exact_domain_registration():
    bank = row("ifsc", {"IFSC": PAY["ifsc"], "BANK": "Example Bank", "CITY": "Pune", "CONTACT": PRIVATE},
               provider="ifsc")
    history = profile(81, [VENDOR, role(71, "2026-08-08", "2026-09-10")], [role(73, "2026-09-20")])
    result = run("payment", bank, company(), person(history), rdap(), inputs=PAY)
    assert card(result, "Next-employer start")["observed_on"] == "2026-08-08"
    assert "11 days" in card(result, "Domain registration")["detail"]
    assert "Example Bank" in card(result, "Bank branch lookup")["detail"]
    assert PRIVATE not in json.dumps(result) and PROFILE not in json.dumps(result)


@pytest.mark.parametrize("past,current", [
    ([VENDOR], []),  # an end date by itself
    ([], [role(21, "2017-01-01")]),  # still-current listing
    ([VENDOR], [role(22, "2026-06-01")]),  # overlapping employment
    ([VENDOR], [role(22, "2026-12-01")]),
    ([VENDOR, role(66, None, "2026-09-01")], [NEXT]),
    ([VENDOR], [NEXT, role(72, "2026-08-08")]),
    ([VENDOR], [NEXT, role(21, "2026-10-01")]),  # returned to vendor
    ([role(21, "2020-01", "2026-08")], [role(71, "2026-08")]),
    ([VENDOR], [role(None, "2026-08-01"), NEXT]),
])
def test_ambiguous_movements_remain_unknown(past, current):
    result = run("payment", company(), person(profile(81, past, current)), inputs=PAY)
    assert all(e["label"] != "Next-employer start" for e in result["evidence"])


@pytest.mark.parametrize("person_row", [
    person(profile(81, [VENDOR], [NEXT]), url=PROFILE + "somebody-else"),
    person(profile(81, [VENDOR], [NEXT]), confidence=0.6),
    row("person_enrich", None, status="unavailable"),
])
def test_unbound_profile_cannot_join_payment_claim(person_row):
    result = run("payment", company(), person_row, rdap(), inputs=PAY)
    assert all(e["label"] != "Next-employer start" for e in result["evidence"])


def test_missing_permission_suppresses_person_evidence_even_with_company_data():
    result = run("payment", company(), person(profile(81, [VENDOR], [NEXT])), rdap(), inputs=PAY,
                 signals=[{"type": "consent_required", "operation": "person_enrich"}])
    assert all(e["operation"] != "person_enrich" for e in result["evidence"])
    assert any(s["name"] == "Profile consent" for s in result["steps"])


@pytest.mark.parametrize("domain,registered", [
    ("unrelated.example", "2026-10-04"), ("vendor-billing.example", None),
    ("vendor-billing.example", "2026-11-01"),
])
def test_missing_or_mismatched_registration_is_not_domain_age(domain, registered):
    result = run("payment", company(), rdap(domain, registered), inputs=PAY)
    assert all(e["label"] != "Domain registration" for e in result["evidence"])


def engineering_counts():
    return company("company_enrich", updated_at="2026-10-10", headcount={
        "by_function_timeseries": {
            "CURRENT_FUNCTION": {"Engineering": [
                {"date": "2023-09-30", "employee_count": 11}, {"date": "2020-09-30", "employee_count": 58}]},
            "GEO_REGION": {"Engineering": [{"date": "2023-09-30", "employee_count": 744}]},
        }, "by_role_absolute": {"Engineering": 120}, "total": 865,
    })


@pytest.mark.parametrize("claim", [
    "Led 40 engineers, 2023 to 2025",
    {"start_date": "2023", "end_date": "2025", "department": "Engineering", "headcount": 40},
    json.dumps({"start_date": "2023", "end_date": "2025", "department": "Engineering", "headcount": 40}),
])
def test_candidate_compares_claim_at_the_requested_dates_and_function(claim):
    result = run("candidate", company(), person(profile(81, [VENDOR])), engineering_counts(),
                 inputs={**INPUTS, "claim": claim}, subject="Candidate")
    counts = card(result, "Claimed headcount")
    assert counts["observed_on"] == "2023-09-30"
    assert all(term in counts["detail"] for term in ("40", "11", "Engineering", "below"))
    assert all(term not in counts["detail"] for term in ("865", "120", "744"))
    assert "covers the claimed period" in card(result, "Claimed employment dates")["detail"]
    assert "verdict" not in result
    assert PRIVATE not in json.dumps(result)


def test_changing_only_the_claim_changes_both_comparisons():
    records = (company(), person(profile(81, [role(21, "2023-01-01", "2024-01-01")])), engineering_counts())
    newer = run("candidate", *records, inputs={**INPUTS, "claim": "Led 40 engineers in Q3 2023"})
    older = run("candidate", *records, inputs={**INPUTS, "claim_start": "2020", "claim_end": "2020",
                                               "claim_headcount": "25", "claim_department": "Engineering"})
    assert "covers the claimed period" in card(newer, "Claimed employment dates")["detail"]
    assert "No documented overlap" in card(older, "Claimed employment dates")["detail"]
    assert "below" in card(newer, "Claimed headcount")["detail"]
    assert "at or above" in card(older, "Claimed headcount")["detail"]
    assert card(older, "Claimed headcount")["observed_on"] == "2020-09-30"


def test_current_headcount_cannot_supply_a_historical_estimate():
    result = run("candidate", company(), engineering_counts(), inputs={**INPUTS, "claim": "Led 40 engineers in Q1 2021"})
    assert all(e["label"] != "Claimed headcount" for e in result["evidence"])
    assert any(s["name"] == "Claimed headcount" and "40" in s["detail"] for s in result["steps"])


def test_undated_team_claim_compares_scope_without_assuming_a_quarter():
    result = run("candidate", company(), engineering_counts(), inputs={**INPUTS, "claim": "Managed 60 engineers"})
    detail = card(result, "Claimed headcount")["detail"]
    assert "60" in detail and "120" in detail and "needs a date" in detail
    assert "below" not in detail


def test_identity_mismatch_between_identify_and_enrich_excludes_headcount():
    conflicting = engineering_counts()
    conflicting["data"][0]["matches"][0]["company_data"]["crustdata_company_id"] = 525
    result = run("candidate", company(), conflicting, inputs={**INPUTS, "claim": "Led 40 engineers in Q3 2023"})
    assert all(e["label"] != "Claimed headcount" for e in result["evidence"])
    assert any(s["name"] == "Company enrichment identity" for s in result["steps"])


def test_peer_aggregation_requires_distinct_other_people_in_claimed_period():
    # All 15 colleagues overlap the full employment history, only five in 2023.
    target = profile(81, [VENDOR])
    in_window = [profile(i + 100, [role(21, "2023-03-01", "2023-08-01")]) for i in range(5)]
    early = [profile(i + 200, [role(21, "2021-01-01", "2021-12-31")]) for i in range(10)]
    title = "Colleague overlap"
    candidates = [target, *in_window, *early, in_window[0], profile(501, [role(999, "2023-01-01", "2023-11-01")])]
    peers = row("person_search", {"profiles": candidates, "total_count": 100_000})
    result = run("candidate", company(), peers, person(target), inputs={**INPUTS, "claim": "2023 to 2023"})
    assert card(result, title)["detail"].startswith("5 distinct")
    peers["data"]["profiles"] = [target, *in_window[:4], *early, early[0], in_window[0]]
    thin = run("candidate", company(), peers, person(target), inputs={**INPUTS, "claim": "2023 to 2023"})
    assert all(e["label"] != title for e in thin["evidence"])
    assert any(s["name"] == title and s["status"] == "insufficient_coverage" for s in thin["steps"])


def test_open_role_does_not_extend_to_a_later_claim_or_peer():
    target = profile(81, [], [role(21, "2018-01-01")])
    peers = row("person_search", {"profiles": [profile(i + 100, [VENDOR]) for i in range(18)]})
    result = run("candidate", person(target), company(), peers, inputs={**INPUTS, "claim": "2024 to 2025"})
    assert "No documented overlap" in card(result, "Claimed employment dates")["detail"]
    assert all(e["label"] != "Colleague overlap" for e in result["evidence"])


def registry(**updates):
    return row("brreg", {"organisasjonsnummer": "123456789", "navn": "Vendor AS",
                         "hjemmeside": "https://www.vendor.example", **updates}, provider="brreg")


def test_independent_vendor_records_pass_the_live_callback_gate(adjudicate):
    result = run("payment", company(), registry(), rdap(), person(profile(81, [VENDOR], [NEXT])),
                 inputs={**PAY, "orgnr": "123456789"})
    assert adjudicate("payment", result)["verdict"] == "HELD"
    by_id = {card["id"]: card for card in result["evidence"]}
    signals = [s for s in result["signals"] if s["claim"] == result["proposition"]]
    assert {by_id[s["evidence_id"]]["source"] for s in signals} == {"Crustdata", "Brønnøysund"}
    assert len(signals) == 2
    assert all(by_id[s["evidence_id"]]["claim"] == s["claim"] for s in result["signals"])
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("registry_row", [
    registry(organisasjonsnummer="123456780"), registry(navn="Different Vendor AS"),
    registry(hjemmeside="other.example"), row("brreg", None, provider="brreg", status="http_503"),
    row("brreg", registry()["data"], provider="crustdata"),
])
def test_unrelated_payment_facts_never_replace_a_missing_domain_witness(registry_row, adjudicate):
    result = run("payment", company(), registry_row, rdap(), person(profile(81, [VENDOR], [NEXT])),
                 inputs={**PAY, "orgnr": "123456789"})
    assert adjudicate("payment", result)["verdict"] != "HELD"
    assert all(e["label"] != "Vendor domain cross-check" for e in result["evidence"])


@pytest.mark.parametrize("sender", ["vendor.example", "billing.vendor.example", "alternate.example"])
def test_vendor_and_a_known_alias_or_subdomain_cannot_trigger_callback(sender, adjudicate):
    identified = company()
    identified["data"][0]["matches"][0]["company_data"]["basic_info"]["all_domains"] = ["alternate.example"]
    result = run("payment", identified, registry(), inputs={**PAY, "sender_domain": sender, "orgnr": "123456789"})
    assert adjudicate("payment", result)["verdict"] != "HELD"


def test_stale_profile_remains_historical_context_and_cannot_vote(adjudicate):
    old = person(profile(81, [VENDOR], [NEXT], updated="2026-08-12"))
    result = run("payment", company(), old, rdap(), inputs=PAY)
    assert card(result, "Next-employer start")["observed_on"] == "2026-08-08"
    assert not any(s["operation"] == "person_enrich" for s in result["signals"])
    assert adjudicate("payment", result)["verdict"] == "INSUFFICIENT WITNESSES"
    assert any(s["name"] == "Profile freshness" and s["status"] == "unknown" for s in result["steps"])


def test_person_identify_and_enrich_must_agree_on_the_person_id(adjudicate):
    identity = person({"crustdata_person_id": 99})
    identity["operation"] = "person_identify"
    result = run("payment", company(), identity, person(profile(81, [VENDOR], [NEXT])), inputs=PAY)
    assert adjudicate("payment", result)["verdict"] == "IDENTITY REVIEW"
    assert all(e["label"] != "Next-employer start" for e in result["evidence"])


def test_company_estimates_and_filing_index_are_independent_facts(adjudicate):
    headcount = {"by_function_timeseries": {"CURRENT_FUNCTION": {"Finance": [
        {"date": "2026-09-30", "employee_count": 19}, {"date": "2026-06-30", "employee_count": 27},
        {"date": "2027-01-01", "employee_count": 9040}]}}}
    listing = {"company": {"basic_info": {"crustdata_company_id": 21}},
               "metadata": {"date_added": "2026-09-29T03:00:00Z"}, "content": {"description": PRIVATE}}
    postings = row("job_search", {"job_listings": [
        listing, {**listing, "company": {"basic_info": {"crustdata_company_id": 72}},
                  "metadata": {"date_added": "2026-10-14"}}]})
    result = run("company", company(), company("company_enrich", headcount=headcount), submissions(), postings)
    finance = card(result, "Finance headcount")
    assert "19" in finance["detail"] and "27" in finance["detail"] and "9040" not in finance["detail"]
    assert card(result, "Indexed job posting")["observed_on"] == "2026-09-29"
    assert finance["claim"] != card(result, "8-K Item 5.02")["claim"]
    assert adjudicate("company", result)["verdict"] == "INSUFFICIENT WITNESSES"
    assert PRIVATE not in json.dumps(result)


def test_executive_start_dates_use_embedded_enrichment_role_schema_and_suppress_small_groups():
    def executive(i):
        return {"crustdata_person_id": i, "basic_profile": {"name": PRIVATE}, "experience": {"employment_details": {
            "current": [{"employer_company_id": ["21"], "employee_start_date": f"2020-02-0{i}"},
                        {"employer_company_id": ["706"], "employee_start_date": "2001-01-01"}]}}}
    leaders = [executive(i) for i in range(1, 6)]
    result = run("company", company(), company("company_enrich", people={"cxos": [*leaders, leaders[0]]}))
    detail = card(result, "Executive role starts")["detail"]
    assert "5 distinct" in detail and "2020-02-01" in detail and "2020-02-05" in detail and "2001" not in detail
    assert PRIVATE not in json.dumps(result)
    thin = run("company", company(), company("company_enrich", people={"cxos": leaders[:-1]}))
    assert all(e["label"] != "Executive role starts" for e in thin["evidence"])


def test_candidate_date_and_staffing_checks_leave_the_employment_decision_with_the_reviewer(adjudicate):
    result = run("candidate", company(), person(profile(81, [VENDOR])), engineering_counts(), submissions(),
                 inputs={**INPUTS, "claim": "Led 40 engineers in Q3 2023"})
    assert result["proposition"] == card(result, "Claimed headcount")["claim"]
    assert {s["provider"] for s in result["signals"]} == {"crustdata"}
    assert adjudicate("candidate", result)["verdict"] == "INSUFFICIENT WITNESSES"


def test_month_precision_survives_projection():
    result = run("payment", company(), person(profile(81, [VENDOR], [role(71, "2026-08")])), inputs=PAY)
    movement = card(result, "Next-employer start")
    assert movement["observed_from"] == "2026-08-01" and movement["observed_through"] == "2026-08-31"
    assert "observed_on" not in movement


def test_explicit_claim_for_another_employer_is_withheld():
    claim = {"start_date": "2023", "end_date": "2025", "headcount": 40,
             "department": "Engineering", "employer_domain": "other.example"}
    result = run("candidate", company(), person(profile(81, [VENDOR])), engineering_counts(),
                 inputs={**INPUTS, "claim": claim})
    assert all(e["label"] not in ("Claimed headcount", "Claimed employment dates") for e in result["evidence"])
    assert any(s["name"] == "Candidate claim" and s["status"] == "unknown" for s in result["steps"])


def test_misaligned_sec_index_cannot_attach_another_rows_date():
    sec = submissions()
    sec["data"]["filings"]["recent"]["filingDate"].pop(3)
    result = run("company", company(), sec)
    assert all(e["source"] != "sec" for e in result["evidence"])


@pytest.mark.parametrize("metadata", [{"status": "http_403"}, {"mode": "REPLAY"}, {"as_of": "unknown"}])
def test_only_dated_live_successes_can_supply_observations(metadata):
    sec = {**submissions(), **metadata}
    result = run("company", company(), sec, signals=[{"type": "claim_observation", "claim": PRIVATE}])
    assert all(e["source"] != "sec" for e in result["evidence"])
    assert not result["signals"] and PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("charge,expected", [("0", 0), ("1.75", 1.75), (None, None), ("NaN", None)])
def test_billing_is_separate_from_witness_count(charge, expected):
    result = interpret("payment", "Vendor", {}, {"credits": [{"actual": charge}]})
    assert result["credits"] == expected and not result["signals"]


@pytest.mark.parametrize("ids,days_old,role_fields,expected", [
    (["21"], 2, {}, True), (["21", "42"], 2, {}, False), (["21"], 180, {}, False),
    (["21"], 2, {"employee_title": "Advisor to the Acting CFO"}, False),
    (["21"], 2, {"employee_end_date": "2020-01-01"}, False),
])
def test_forward_review_needs_bound_fresh_interim_role_and_recent_issuer_filing(ids, days_old, role_fields, expected, adjudicate):
    today = datetime.now(timezone.utc).date()
    start = str(today - timedelta(days=16))
    filed = str(today - timedelta(days=14))
    refreshed = str(today - timedelta(days=days_old))
    officer = {"crustdata_person_id": 81, "updated_at": refreshed, "basic_profile": {"name": PRIVATE},
               "experience": {"employment_details": {"current": [
                   {"employer_company_id": ids, "employee_title": "Acting Chief Financial Officer",
                    "employee_start_date": start, **role_fields}]}}}
    enrich = company("company_enrich", people={"cxos": [officer]})
    sec = submissions(filings={"recent": {"form": ["8-K"], "items": ["5.02,9.01"], "filingDate": [filed]}})
    records = [{**r, "as_of": str(today)} for r in (company(), enrich, sec)]
    result = run("company", *records)
    assert ("forecast" in result) is expected
    if expected:
        assert adjudicate("company", result)["verdict"] == "FORECAST FOR REVIEW"
        assert result["forecast"]["filing_on"] == filed
        assert result["forecast"]["due"] > str(today)
        assert card(result, "Interim finance appointment")["observed_on"] == start
    assert PRIVATE not in json.dumps(result)


def test_bank_validation_minimizes_private_account_identifiers_and_never_votes():
    iban = "DE89370400440532013000"
    data = {"iban": iban, "valid": True, "bankData": {"accountNumber": PRIVATE}, "messages": [PRIVATE]}
    lookup = row("openiban", data, provider="openiban")
    lookup["source"] = "https://openiban.com/validate/" + iban
    result = run("payment", lookup, inputs={"iban": iban})
    assert "passed" in card(result, "IBAN validation")["detail"]
    assert iban not in json.dumps(result) and PRIVATE not in json.dumps(result)
    assert result["signals"] == []


def test_interpret_accepts_the_transport_output_directly(monkeypatch):
    class Response(io.BytesIO):
        headers = {}
        code = 200

    class PublicIndex:
        def open(self, request, timeout):
            assert request.full_url == "https://data.sec.gov/submissions/CIK0000000042.json"
            body = {"name": "Vendor Inc.", "cik": "0000000042", "tickers": ["VEND"], "filings": {"recent": {
                "form": ["8-K"], "items": ["5.02,9.01"], "filingDate": ["2020-05-06"], "reportDate": ["2020-05-01"]}}}
            return Response(json.dumps(body).encode())

    monkeypatch.setenv("SEC_USER_AGENT", "test")
    monkeypatch.setattr(providers, "build_opener", lambda *_: PublicIndex())
    monkeypatch.setattr(providers, "throttle", lambda *_: None)
    inputs = {"cik": "42"}
    raw = providers.run_live("company", "", inputs=inputs)
    result = interpret("company", "VEND", inputs, raw)
    filing = card(result, "8-K Item 5.02")
    assert filing["observed_on"] == "2020-05-06" and filing["as_of"] == raw["evidence"][0]["as_of"]
    assert result["signals"][0]["evidence_id"] == filing["id"] and result["proposition"] == filing["claim"]


def test_function_headcount_uses_the_returned_function_without_echoing_arbitrary_claim_text():
    enriched = company("company_enrich", headcount={"by_function_timeseries": {"CURRENT_FUNCTION": {
        "Human Resources": [{"date": "2023-05-01", "employee_count": 16}]}}})
    scope = {"start_date": "2023", "end_date": "2023", "headcount": 30, "department": "human resources"}
    result = run("candidate", company(), enriched, inputs={**INPUTS, "claim": scope})
    assert "16 profiles" in card(result, "Claimed headcount")["detail"]
    scope["department"] = PRIVATE
    unknown = run("candidate", company(), enriched, inputs={**INPUTS, "claim": scope})
    assert PRIVATE not in json.dumps(unknown)
    assert all(e["label"] != "Claimed headcount" for e in unknown["evidence"])


def test_negative_team_statement_is_left_for_review():
    result = run("candidate", company(), engineering_counts(), inputs={**INPUTS, "claim": "Never led 40 engineers in Q3 2023"})
    assert all(e["label"] != "Claimed headcount" for e in result["evidence"])
    assert not result["signals"]


def test_live_candidate_intake_uses_the_claim_and_its_actual_witness(monkeypatch, adjudicate):
    from backend import live

    candidate = profile(81, [VENDOR])
    identity = {**person({"crustdata_person_id": 81}), "operation": "person_identify"}
    records = {r["operation"]: r for r in (
        company(), engineering_counts(), identity, person(candidate), row("person_search", {"profiles": []}))}

    def collect(desk, subject, consent, lane):
        assert consent is True
        selected = [records[op] for op in lane["crustdata"]]
        return dict(evidence=selected, signals=[], steps=[], credits=[], flows=[])

    monkeypatch.setattr(live, "run_live", collect)
    inputs = {"domain": "vendor.example", "person_url": PROFILE, "claim": "Led 40 engineers in Q3 2023"}
    result = live.collect_live("candidate", "Candidate", consent=True, inputs=inputs)
    count = card(result, "Claimed headcount")
    assert "40" in count["detail"] and "11 profiles" in count["detail"] and count["observed_on"] == "2023-09-30"
    assert result["proposition"] == count["claim"]
    assert any(s["evidence_id"] == count["id"] and s["provider"] == "crustdata" for s in result["signals"])
    assert adjudicate("candidate", result)["verdict"] == "INSUFFICIENT WITNESSES"
