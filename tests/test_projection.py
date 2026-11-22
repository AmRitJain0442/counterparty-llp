from backend.colleagues import overlap_count
from backend.observations import describe


def profile(pid, start, end):
    return {"crustdata_person_id": pid, "experience": {"employment_details": {
        "past": [{"crustdata_company_id": 19, "start_date": start, "end_date": end}]}}}


def test_overlap_counts_unique_colleagues_only():
    subject = profile(1, "2020-01-01", "2021-05-01")
    peer = profile(2, "2019-01-01", "2020-06-30")
    later = profile(3, "2022-01-01", None)
    assert overlap_count(subject, {"profiles": [subject, peer, peer, later]}, 19) == 1


def test_missing_exit_does_not_imply_current_overlap():
    subject = profile(1, "2020-01-01", None)
    assert overlap_count(subject, {"profiles": [profile(2, "2024-01-01", None)]}, 19) == 0


def test_enrichment_projection_minimizes_people_and_small_counts():
    row = {"operation": "company_enrich", "status": "ok", "data": [{"matches": [{
        "company_data": {"headcount": {"total": 3}, "people": {"founders": ["PRIVATE NAME"]}}
    }]}]}
    detail = describe(row)
    assert "PRIVATE NAME" not in detail and "3" not in detail


def test_rdap_date_requires_registration_event():
    row = {"operation": "rdap", "status": "ok", "data": {"events": [
        {"eventAction": "last changed", "eventDate": "2026-01-01"}]}}
    assert "2026" not in describe(row)
