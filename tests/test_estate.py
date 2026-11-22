import json
from datetime import date, datetime, timezone
from unittest.mock import Mock, call

import pytest
import requests

from backend import estate


FILING = "2024-04-01"
CUTOFF = "2024-06-30"
COMPANY = {"crustdata_company_id": 41, "basic_info": {
    "crustdata_company_id": 41, "name": "Estate AS", "primary_domain": "estate.example"}}
PRIVATE = "Private Worker Sentinel"


def role(cid, site, start, end=None, name=None):
    return {"crustdata_company_id": cid, "company_website": site, "name": name,
            "start_date": start, "end_date": end, "title": PRIVATE}


OLD = role(41, "https://www.estate.example/about", "2020-01-01", "2024-03-31", "Estate AS")
NEXT = role(72, "https://next.example", FILING, name="Next Employer AS")
SMALL = role(89, "small.example", "2024-05-02", name="Small Group AS")


def person(i, past=(), current=()):
    return {"crustdata_person_id": 94520000 + i,
            "basic_profile": {"name": PRIVATE, "date_of_birth": "1973-09-21"},
            "social_handles": {"profile_url": "https://network.example/in/private-worker"},
            "experience": {"employment_details": {"past": list(past), "current": list(current)}}}


def movers(n, past=(OLD,), current=(NEXT,), offset=0):
    return [person(i + offset, past, current) for i in range(n)]


def stale(n, offset):
    return movers(n, (), ({**OLD, "end_date": None},), offset)


def page(profiles, cursor=None, total=None):
    return {"profiles": profiles, "total_count": len(profiles) if total is None else total, "next_cursor": cursor}


def response(data, credits="1.25", status=200):
    result = requests.Response()
    result.status_code = status
    if credits is not None:
        result.headers["X-Credits-Used"] = credits
    result._content = json.dumps(data).encode()
    result._content_consumed = True
    return result


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test-key-sentinel")
    post, throttle = Mock(), Mock()
    monkeypatch.setattr(estate.requests, "post", post)
    monkeypatch.setattr(estate, "throttle", throttle)
    return post, throttle


def investigate(company=COMPANY, domain="estate.example", filing=FILING, cutoff=CUTOFF):
    return estate.estate_evidence(PRIVATE, domain, company, filing, cutoff)


def test_scoped_search_paging_projection_and_thresholds(provider):
    post, throttle = provider
    rows = movers(5) + movers(4, current=(SMALL,), offset=5) + stale(6, 9)
    post.side_effect = [response(page(rows[:8], "private-cursor", 15), "1.25"),
                        response(page(rows[7:], total=15), ".10")]
    result = investigate(domain="unverified.example", cutoff=datetime(2024, 6, 30, tzinfo=timezone.utc))

    assert result["status"] == "ok"
    assert result["coverage"] == 15 and result["unknown"] == 10
    assert result["flows"] == [{"from": "estate.example", "to": "next.example", "count": 5}]
    assert result["credits"] == 1.35
    assert post.call_count == 2
    first, second = post.call_args_list
    assert first.args == ("https://api.crustdata.com/person/search",)
    assert first.kwargs["headers"]["x-api-version"] == "2025-11-01"
    assert first.kwargs["headers"]["Authorization"] == "Bearer test-key-sentinel"
    assert first.kwargs["allow_redirects"] is False
    query = first.kwargs["json"]
    assert query["filters"] == {"field": "experience.employment_details.company_id", "type": "=", "value": 41}
    assert sorted(query["fields"]) == sorted(["crustdata_person_id"] + [
        f"experience.employment_details.{section}.{field}" for section in ("current", "past")
        for field in ("crustdata_company_id", "company_website", "start_date", "end_date")])
    assert second.kwargs["json"] == {**query, "cursor": "private-cursor"}
    assert throttle.call_args_list == [call("crustdataperson_search", 12), call("crustdata:overall", .6)] * 2
    assert result["evidence"][0]["as_of"] == result["as_of"]
    assert result["evidence"][0]["mode"] == "LIVE"
    public = json.dumps(result, allow_nan=False)
    for secret in (PRIVATE, "1973-09-21", "private-worker", "private-cursor", "94520000",
                   "test-key-sentinel", "Small Group", "small.example", "unverified.example"):
        assert secret not in public


def test_verified_domain_query_and_employer_identity(provider):
    post, _ = provider
    # The search uses a bare domain. Positions return a URL and may have no ID.
    old = {**OLD, "crustdata_company_id": None}
    new = {**NEXT, "crustdata_company_id": None, "name": PRIVATE}
    rows = movers(4, (old,), (new,)) + movers(1, (OLD,), ({**NEXT, "name": PRIVATE},), 4) + stale(10, 5)
    rows += movers(5, (role(84, "not-estate.example", "2020", FILING, "Estate AS"),), (SMALL,), 15)
    post.return_value = response(page(rows))
    result = investigate({"basic_info": {"primary_domain": "estate.example"}}, domain="unverified.example")
    assert post.call_args.kwargs["json"]["filters"] == {
        "field": "experience.employment_details.company_website_domain", "type": "=", "value": "estate.example"}
    assert result["coverage"] == 15
    assert result["flows"] == [{"from": "estate.example", "to": "next.example", "count": 5}]
    assert PRIVATE not in json.dumps(result)


def test_same_domain_does_not_override_distinct_ids(provider):
    post, _ = provider
    other = {**OLD, "crustdata_company_id": 99}
    post.return_value = response(page(movers(14) + movers(5, (other,), (NEXT,), 14)))
    result = investigate()
    assert result["coverage"] == 14
    assert result["status"] == "insufficient_coverage" and not result["flows"]

    result = investigate({"basic_info": {"website": "https://estate.example"}})
    assert result["status"] == "unresolved_company" and not result["flows"]


def test_distinct_destination_ids_and_small_domain_labels(provider):
    post, _ = provider
    other = {**NEXT, "crustdata_company_id": 73}
    # Shared destination domain, plus a personal website from one profile.
    rows = movers(4) + movers(1, current=({**NEXT, "company_website": "private-worker.example"},), offset=4)
    rows += movers(5, current=(other,), offset=5) + stale(5, 10)
    post.return_value = response(page(rows))
    result = investigate(41)
    assert result["flows"] == [
        {"from": "Crustdata company 41", "to": "Crustdata company 72", "count": 5},
        {"from": "Crustdata company 41", "to": "Crustdata company 73", "count": 5},
    ]
    assert "private-worker" not in json.dumps(result)


@pytest.mark.parametrize("company,filing,cutoff,status", [
    (None, FILING, CUTOFF, "unresolved_company"),
    ({"basic_info": {"name": "Estate AS"}}, FILING, CUTOFF, "unresolved_company"),
    ({"crustdata_company_id": 42, "basic_info": {"crustdata_company_id": 41}}, FILING, CUTOFF, "unresolved_company"),
    (True, FILING, CUTOFF, "unresolved_company"),
    (COMPANY, None, CUTOFF, "invalid_window"),
    (COMPANY, "2024-02-30", CUTOFF, "invalid_window"),
    (COMPANY, CUTOFF, FILING, "invalid_window"),
    (COMPANY, CUTOFF, "9999-01-01", "invalid_window"),
])
def test_invalid_scope_or_dates_never_search(provider, company, filing, cutoff, status):
    result = investigate(company, filing=filing, cutoff=cutoff)
    provider[0].assert_not_called()
    assert result["status"] == status
    assert result["coverage"] is None and result["credits"] is None and not result["flows"]


def test_missing_key_never_searches(provider, monkeypatch):
    monkeypatch.delenv("CRUSTDATA_API_KEY")
    assert investigate()["status"] == "unavailable"
    provider[0].assert_not_called()


@pytest.mark.parametrize("n,status", [(0, "insufficient_coverage"), (14, "insufficient_coverage"), (15, "ok")])
def test_unique_coverage_boundary(provider, n, status):
    post, _ = provider
    rows = movers(n)
    post.return_value = response(page(rows + rows, total=n))
    result = investigate()
    assert result["coverage"] == n and result["status"] == status
    assert [f["count"] for f in result["flows"]] == ([15] if n == 15 else [])


def test_later_joiners_and_unmatched_profiles_cannot_supply_coverage(provider):
    late = {**OLD, "start_date": "2024-04-04", "end_date": None}
    provider[0].return_value = response(page(movers(14) + movers(1, (), (late,), 14) + [person(15)]))
    result = investigate()
    assert result["coverage"] == 14 and result["status"] == "insufficient_coverage"
    assert not result["flows"]


@pytest.mark.parametrize("past,current,destination", [
    # The next appointment can itself be in past; neither array is ordered.
    ([{**NEXT, "end_date": "2024-05-04"}, OLD], [{**SMALL, "start_date": "2024-05-06"}], "next.example"),
    ([OLD], [{**NEXT, "start_date": CUTOFF}], "next.example"),
    ([OLD], [{**NEXT, "start_date": "2024-05"}], "next.example"),
    ([OLD], [{**NEXT, "start_date": "2024-07-01T00:30:00+02:00"}], "next.example"),
    ([OLD], [{**NEXT, "end_date": "  "}], "next.example"),
    ([OLD], [{**NEXT, "start_date": "2024-07-01"}], None),
    # A pre-filing move, followed by another job inside the window.
    ([{**OLD, "end_date": "2024-01-01"}, {**SMALL, "start_date": "2024-01-02", "end_date": "2024-03-01"}],
     [NEXT], None),
    # A foreign concurrent appointment is ambiguous, even if the person also lists a later job.
    ([OLD, {**SMALL, "start_date": "2024-03-02", "end_date": "2024-04-02"}], [NEXT], None),
    ([OLD], [NEXT, {**SMALL, "start_date": FILING}], None),
    ([{**OLD, "start_date": FILING, "end_date": FILING}], [NEXT], None),
    ([OLD], [{**NEXT, "start_date": "2024"}], None),
    ([OLD], [{**NEXT, "start_date": None}], None),
    ([OLD], [{**NEXT, "start_date": "bad-date"}], None),
    ([{**OLD, "end_date": None}], [NEXT], None),
    ([OLD], [NEXT, {**OLD, "end_date": None}], None),
    ([OLD, {**SMALL, "start_date": None, "end_date": "2024-04-20"}], [NEXT], None),
    ([OLD, role(None, None, FILING, "2024-04-20", PRIVATE)], [{**NEXT, "start_date": "2024-05-01"}], None),
    # An internal promotion can extend the estate stint across filing.
    ([{**OLD, "end_date": FILING}, {**OLD, "start_date": FILING, "end_date": "2024-04-30"}],
     [{**NEXT, "start_date": "2024-05-01"}], "next.example"),
    # A rehire after the first external move does not rewrite that move.
    ([OLD, {**NEXT, "end_date": "2024-04-30"}], [{**OLD, "start_date": "2024-05-01", "end_date": None}],
     "next.example"),
], ids=["past-destination", "inclusive-cutoff", "month-precision", "utc-cutoff", "blank-current-end", "future-start",
        "intervening-employer", "overlap", "simultaneous-employers", "same-day-both-start", "uncertain-year", "missing-next-start",
        "invalid-date", "missing-estate-end", "still-lists-estate", "undatable-intervening-role",
        "unresolved-intervening-employer", "promotion", "later-rehire"])
def test_dated_first_employer(provider, past, current, destination):
    provider[0].return_value = response(page(movers(15, past, current)))
    result = investigate(filing=date.fromisoformat(FILING))
    assert result["status"] == "ok" and result["coverage"] == 15
    assert [(f["to"], f["count"]) for f in result["flows"]] == ([(destination, 15)] if destination else [])


def test_conflicting_duplicates_and_incomplete_histories(provider):
    post, _ = provider
    rows = movers(4) + movers(1, (OLD,), ({**NEXT, "name": PRIVATE},), 4)
    rows += movers(1, offset=5) + movers(1, current=(SMALL,), offset=5)
    incomplete = person(6, [OLD, {**NEXT, "end_date": CUTOFF}])
    del incomplete["experience"]["employment_details"]["current"]
    post.return_value = response(page(rows + [incomplete] + stale(8, 7), total=15))
    result = investigate()
    assert result["coverage"] == 15 and result["unknown"] == 10
    assert result["flows"] == [{"from": "estate.example", "to": "next.example", "count": 5}]
    assert PRIVATE not in json.dumps(result)


def test_small_residual_has_no_public_bucket(provider):
    provider[0].return_value = response(page(movers(14) + stale(1, 14)))
    result = investigate()
    assert result["flows"][0]["count"] == 14 and result["unknown"] is None


@pytest.mark.parametrize("failure,step_status,credits", [
    (response({"error": PRIVATE}, ".25", 429), "rate_limited", 1.5),
    (response({"error": PRIVATE}, None, 403), "http_403", None),
    (requests.Timeout(PRIVATE), "transport_or_decode_failure", None),
    (response({"profiles": {}}, "0"), "invalid_page", 1.25),
    (response(page(movers(1, offset=15), "secret-cursor", 16), "0"), "invalid_cursor", 1.25),
    (response(page([], total=16), "0"), "incomplete_page", 1.25),
    (response(page([], total=0), "0"), "total_changed", 1.25),
], ids=["rate-limit", "access-denied", "timeout", "invalid-profiles", "cursor-loop", "short-page", "total-drift"])
def test_interrupted_search_preserves_progress_without_publishing_flows(provider, failure, step_status, credits):
    post, _ = provider
    post.side_effect = [response(page(movers(15), "secret-cursor", 16)), failure]
    result = investigate()
    assert post.call_count == 2 and result["status"] == "partial"
    assert result["coverage"] >= 15 and result["unknown"] is None and not result["flows"]
    assert result["steps"][1]["status"] == step_status and result["steps"][0]["credits"] == 1.25
    assert result["credits"] == credits
    assert not any(secret in json.dumps(result) for secret in (PRIVATE, "secret-cursor", "test-key-sentinel"))


def test_budget_and_truncated_page_are_partial(provider, monkeypatch):
    post, _ = provider
    monkeypatch.setattr(estate, "MAX_PAGES", 1)
    post.return_value = response(page(movers(15), "a-cursor", 20000))
    result = investigate()
    assert not result["flows"] and result["status"] == "partial"
    assert result["steps"][0]["status"] == "page_limit" and result["coverage"] == 15
    post.return_value = response({"profiles": movers(15), "total_count": 15})
    assert investigate()["status"] == "partial"
    post.return_value = response(page(movers(15) + [{"basic_profile": {"name": PRIVATE}}]))
    assert investigate()["status"] == "partial"


def test_interrupted_response_body_keeps_header_charge(provider):
    post, _ = provider
    interrupted = response({}, ".75")
    interrupted.iter_content = Mock(side_effect=requests.exceptions.ChunkedEncodingError(PRIVATE))
    post.side_effect = [response(page(movers(15), "cursor", 16)), interrupted]
    result = investigate()
    assert result["status"] == "partial" and result["coverage"] == 15
    assert not result["flows"] and result["credits"] == 2
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("header,expected", [(None, None), ("NaN", None), ("-1", None), ("invalid", None), ("0", 0)])
def test_unusable_first_response_does_not_become_zero_coverage(provider, header, expected):
    provider[0].return_value = response({"error": PRIVATE}, header, 503)
    result = investigate()
    assert result["coverage"] is None and result["status"] == "unavailable" and not result["flows"]
    assert result["credits"] == expected and PRIVATE not in json.dumps(result, allow_nan=False)
