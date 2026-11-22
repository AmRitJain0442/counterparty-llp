import copy
import json

import pytest

from backend.findings import interpret


def company(operation, **extra):
    return {"provider": "crustdata", "operation": operation, "status": "ok", "as_of": "2026-10-15",
            "data": [{"match_type": "crustdata_company_id", "matched_on": "21", "matches": [
                {"confidence_score": 1, "company_data": {"crustdata_company_id": 21,
                 "basic_info": {"name": "Vendor Inc.", "primary_domain": "vendor.example"}, **extra}}]}]}


def officer(**overrides):
    return {"crustdata_person_id": 81, "basic_profile": {"name": "Alex Example", "last_updated": "2026-10-12"},
            "experience": {"employment_details": {"current": [{"employer_company_id": ["21"],
                "employer_website": ["https://vendor.example"], "employee_title": "Chief Financial Officer",
                "employee_start_date": "2024-01-01"}]}}, **overrides}


def run(profiles, *, subject="Vendor Inc.", inputs=None, **extra):
    fields = {"domain": "vendor.example", "executive_name": "Alex Example", **(inputs or {})}
    return interpret("company", subject, fields, {"evidence": [company("company_identify"),
        company("company_enrich", people={"cxos": profiles}, **extra)]})


def test_separate_company_and_executive_fields_report_one_provider_role():
    result = run([officer()], inputs={"executive_title": "Chief Financial Officer"})
    leadership = result["leadership_review"]
    assert leadership["verdict"] == "ROLE REPORTED"
    assert "Chief Financial Officer" in leadership["summary"]
    assert "one provider" in leadership["summary"] and "independent confirmation" in leadership["summary"]
    assert any(e["label"] == "Named executive role" for e in result["evidence"])
    assert not result["signals"]  # Single source role report does not pass the proposition gate.


def test_legacy_person_subject_keeps_company_identity_gate_and_explains_fields():
    result = run([officer()], subject="Alex Example")
    assert result["leadership_review"]["verdict"] == "ROLE REVIEW"
    step = next(s for s in result["steps"] if s["name"] == "Company identity")
    assert "company subject" in step["detail"] and "separate executive fields" in step["detail"]
    assert not result["evidence"]


@pytest.mark.parametrize("profiles", [[], [officer(basic_profile={"name": "OTHER-PRIVATE-IDENTITY"})]])
def test_absent_or_irrelevant_people_are_incomplete_coverage_not_negative_evidence(profiles):
    result = run(profiles, headcount={"total": 500}, funding={"total_investment_usd": 999999})
    assert result["leadership_review"]["verdict"] == "ROLE REVIEW"
    assert "coverage may be incomplete" in result["leadership_review"]["summary"]
    assert "OTHER-PRIVATE-IDENTITY" not in json.dumps(result)
    assert not any(e["label"] == "Named executive role" for e in result["evidence"])


@pytest.mark.parametrize("patch", [
    {"employer_company_id": ["72"]}, {"employer_company_id": ["21", "72"]},
    {"employer_website": ["other.example"]}, {"employee_end_date": "2026-10-14"},
    {"employee_start_date": "2027-01-01"}, {"employee_start_date": None},
    {"employee_end_date": "unknown"}, {"employee_title": None}, {"is_current": False},
])
def test_misbound_or_conflicting_role_rows_cannot_report_current_role(patch):
    person = officer()
    person["experience"]["employment_details"]["current"][0].update(patch)
    assert run([person])["leadership_review"]["verdict"] == "ROLE REVIEW"


@pytest.mark.parametrize("refresh", [None, "2025-01-01", "2026-10-16", "invalid"])
def test_missing_stale_and_future_refresh_do_not_report_role(refresh):
    person = officer(basic_profile={"name": "Alex Example", "last_updated": refresh})
    assert run([person])["leadership_review"]["verdict"] == "ROLE REVIEW"


def test_duplicate_names_conflicts_and_identical_duplicate_rows():
    person = officer()
    assert run([person, copy.deepcopy(person)])["leadership_review"]["verdict"] == "ROLE REPORTED"
    assert run([person, officer(crustdata_person_id=82)])["leadership_review"]["verdict"] == "ROLE REVIEW"
    changed = copy.deepcopy(person)
    changed["experience"]["employment_details"]["current"][0]["employee_title"] = "CEO"
    assert run([person, changed])["leadership_review"]["verdict"] == "ROLE REVIEW"


def test_title_mismatch_and_unrelated_company_facts_cannot_establish_claim():
    result = run([officer()], inputs={"executive_title": "CEO"}, headcount={"total": 1000})
    assert result["leadership_review"]["verdict"] == "ROLE REVIEW"
    assert "does not exactly match" in result["leadership_review"]["summary"]


def test_enrichment_from_another_company_cannot_supply_role():
    identity = company("company_identify")
    enrichment = company("company_enrich", people={"cxos": [officer()]})
    enrichment["data"][0]["matches"][0]["company_data"]["crustdata_company_id"] = 72
    result = interpret("company", "Vendor Inc.", {"domain": "vendor.example", "executive_name": "Alex Example"},
                       {"evidence": [identity, enrichment]})
    assert result["leadership_review"]["verdict"] == "ROLE REVIEW"


def test_no_executive_request_keeps_existing_result_shape():
    result = interpret("company", "Vendor Inc.", {"domain": "vendor.example"},
                       {"evidence": [company("company_enrich", people={"cxos": [officer()]})]})
    assert "leadership_review" not in result


def test_repeated_leadership_groups_empirical_dates_and_compound_title():
    person = officer(updated_at="2026-10-12T11:00:34.002Z")
    role = person["experience"]["employment_details"]["current"][0]
    role.update(employee_title="Co-founder, CPTO", employee_start_date="2018-10-01T00:00:00.000Z")
    result = interpret("company", "Vendor Inc.", {"domain": "vendor.example", "executive_name": "Alex Example",
        "executive_title": "Chief Product and Technology Officer"}, {"evidence": [company("company_identify"),
        company("company_enrich", people={"cxos": [], "founders": [person], "decision_makers": [copy.deepcopy(person)]})]})
    assert result["leadership_review"]["verdict"] == "ROLE REPORTED"
    assert result["leadership_review"]["reported_title"] == "Co-founder, CPTO"


@pytest.mark.parametrize("claimed,reported,expected", [
    ("CPO", "Chief Product Officer", True), ("CPTO", "Chief Product and Technology Officer", True),
    ("CPTO", "CPO", False), ("CPTO", "CTO", False), ("CEO", "Advisor to CEO", False),
    ("CPO", "Co-founder, CPTO", False), ("", "CEO", False),
])
def test_exact_title_aliases_preserve_distinct_roles(claimed, reported, expected):
    from backend.findings import executive_titles_match
    assert executive_titles_match(claimed, reported) is expected


def test_stale_role_preserves_dated_report_without_current_role_claim():
    result = run([officer(updated_at="2025-10-01")])
    report = result["leadership_review"]
    assert report["verdict"] == "ROLE REVIEW"
    assert report["reported_title"] == "Chief Financial Officer"
    assert "2025-10-01" in report["summary"] and "30-day" in report["summary"]
    assert any(e["label"] == "Named executive role" for e in result["evidence"])
