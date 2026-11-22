"""Aggregate, retrospective estate evidence from the indexed Crustdata Person Search."""

import calendar
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import NamedTuple
from urllib.parse import urlsplit

import requests

from .providers import throttle


SEARCH_URL = "https://api.crustdata.com/person/search"
EMPLOYMENT = "experience.employment_details"
MIN_COVERAGE = 15
MIN_GROUP = 5
PAGE_SIZE = 50
MAX_PAGES = 5
FIELDS = ["crustdata_person_id"] + [
    f"{EMPLOYMENT}.{section}.{field}"
    for section in ("current", "past")
    for field in ("crustdata_company_id", "company_website", "start_date", "end_date")
]


def _id(value):
    return value if type(value) is int and value > 0 else None


def _domain(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        url = urlsplit(value if "://" in value else "//" + value)
        if url.scheme not in ("", "https", "http") or url.username is not None:
            return None
        host = (url.hostname or "").rstrip(".").removeprefix("www.").encode("idna").decode()
    except (ValueError, UnicodeError):
        return None
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(host) <= 253 and re.fullmatch(rf"(?:{label}\.)+(?:[a-z]{{2,63}}|xn--{label})", host):
        return host
    return None


def _identity(record, domain):
    if not isinstance(record, dict):
        return _id(record), []
    basic = record.get("basic_info", record)
    if not isinstance(basic, dict):
        return None, []
    outer, inner = _id(record.get("crustdata_company_id")), _id(basic.get("crustdata_company_id"))
    if outer and inner and outer != inner:
        return None, []
    aliases = basic.get("all_domains")
    values = [basic.get("primary_domain"), basic.get("website"), *(aliases if isinstance(aliases, list) else [])]
    domains = list(dict.fromkeys(host for value in values if (host := _domain(value))))
    requested = _domain(domain)
    if requested in domains:
        domains.remove(requested)
        domains.insert(0, requested)
    return outer or inner, domains


def _day(value):
    try:
        if isinstance(value, str):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[Tt ].+)?", value):
                return None
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, datetime):
            return (value.astimezone(timezone.utc) if value.tzinfo else value).date()
        return value if isinstance(value, date) else None
    except (ValueError, OverflowError):
        return None


class Period(NamedTuple):
    first: date
    last: date


def _role_date(value):
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        return None, True
    day = _day(value)
    if day:
        return Period(day, day), True
    if isinstance(value, str) and re.fullmatch(r"\d{4}(?:-\d{2})?", value):
        year = int(value[:4])
        month = int(value[5:]) if len(value) == 7 else None
        try:
            start = date(year, 1 if month is None else month, 1)
            last_month = 12 if month is None else month
            return Period(start, date(year, last_month, calendar.monthrange(year, last_month)[1])), True
        except ValueError:
            pass
    return None, False


class Position(NamedTuple):
    cid: int | None
    domain: str | None
    start: Period | None
    end: Period | None
    current: bool


def _history(profile):
    experience = profile.get("experience")
    details = experience.get("employment_details") if isinstance(experience, dict) else None
    roles = set()
    complete = True
    for section in ("past", "current"):
        rows = details.get(section) if isinstance(details, dict) else None
        if not isinstance(rows, list):
            complete = False
            continue
        for row in rows:
            if not isinstance(row, dict):
                complete = False
                continue
            start, start_valid = _role_date(row.get("start_date"))
            end, end_valid = _role_date(row.get("end_date"))
            if not start_valid or not end_valid or (start and end and start.first > end.last):
                complete = False
            roles.add(Position(_id(row.get("crustdata_company_id")), _domain(row.get("company_website")),
                               start, end, section == "current"))
    return roles, complete


def _next_employer(roles, key, origin, filing, cutoff):
    # Start at the last estate tenure already evidenced by filing. Promotions
    # and repeat listings at the same company cannot create external moves.
    estate = {r for r in roles if key(r) == origin and
              ((r.start and r.start.last <= filing) or (r.end and r.end.last <= filing))}
    remaining = roles - estate
    earliest_end = latest_end = latest_start = date.min
    while estate:
        if any(r.current or not r.end for r in estate):
            return None
        earliest_end = max(earliest_end, max(r.end.first for r in estate))
        latest_end = max(latest_end, max(r.end.last for r in estate))
        latest_start = max(latest_start, max((r.start.last for r in estate if r.start), default=date.min))
        possible = [r for r in remaining if (not r.end or r.end.last >= earliest_end)
                    and (not r.start or r.start.first <= cutoff)]
        if not possible or any(not r.start for r in possible):
            return None
        # Select the immediate next position BEFORE applying the filing window.
        # Otherwise an intervening pre-filing employer could be skipped.
        first_by = min(r.start.last for r in possible)
        first = {r for r in possible if r.start.first <= first_by}
        employers = {key(r) for r in first}
        if employers == {origin}:
            estate = first
            remaining -= first
            continue
        first_from = min(r.start.first for r in first)
        if (len(employers) == 1 and latest_start < first_from
                and max(latest_end, filing) <= first_from and first_by <= cutoff):
            employer = employers.pop()
            if employer is not None:
                return employer, {r.domain for r in first if r.domain}
        return None
    return None


def _aggregate(histories, cid, domains, filing, cutoff, complete_search):
    # A shared domain cannot merge two legal entities. An unambiguous domain
    # can connect a domain-only position to a position carrying a company ID.
    ids = defaultdict(set)
    for roles, _ in histories.values():
        for r in roles:
            if r.cid and r.domain:
                ids[r.domain].add(r.cid)
    if cid:
        for host in domains:
            ids[host].add(cid)

    def domain_key(host):
        matches = ids.get(host)
        if not matches:
            return host
        return next(iter(matches)) if len(matches) == 1 else None

    domain_ids = set().union(*(ids[host] for host in domains))
    if not cid and len(domain_ids) > 1:
        return None, None, []
    origin = cid or next(iter(domain_ids), None) or domains[0]

    def key(role):
        if not role.cid and role.domain in domains and len(ids[role.domain]) <= 1:
            return origin
        return role.cid or domain_key(role.domain)

    coverage = 0
    counts = Counter()
    domain_votes = defaultdict(Counter)
    for roles, complete in histories.values():
        if any(key(r) == origin and (not r.start or r.start.first <= filing) for r in roles):
            coverage += 1
            if complete_search and complete:
                movement = _next_employer(roles, key, origin, filing, cutoff)
                if movement:
                    target, hosts = movement
                    counts[target] += 1
                    domain_votes[target].update(hosts)

    def label(company, hosts):
        for host in hosts:
            if domain_key(host) == company:
                return host
        return f"Crustdata company {company}" if isinstance(company, int) else company

    flows = []
    if complete_search and coverage >= MIN_COVERAGE:
        for target, count in counts.items():
            if count >= MIN_GROUP:
                votes = domain_votes[target]
                hosts = sorted((host for host in votes if votes[host] >= MIN_GROUP), key=lambda h: (-votes[h], h))
                flows.append({"from": label(origin, domains), "to": label(target, hosts), "count": count})
    flows.sort(key=lambda flow: (-flow["count"], flow["to"]))
    remainder = coverage - sum(flow["count"] for flow in flows)
    return coverage, remainder if remainder == 0 or remainder >= MIN_GROUP else None, flows


def _credits(header):
    try:
        value = Decimal(header)
        if value.is_finite() and 0 <= value and value.adjusted() < 300:
            return value
    except (InvalidOperation, TypeError, ValueError):
        pass
    return None


def _search_page(payload, api_key):
    throttle("crustdataperson_search", 12)
    throttle("crustdata:overall", .6)
    used = None
    try:
        with requests.post(SEARCH_URL, json=payload, timeout=(5, 20), stream=True, allow_redirects=False,
                           headers={"Authorization": f"Bearer {api_key}", "x-api-version": "2025-11-01"}) as response:
            used = _credits(response.headers.get("X-Credits-Used"))
            if response.status_code != 200:
                status = "rate_limited" if response.status_code == 429 else f"http_{response.status_code}"
                return status, None, used
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 4_000_000:
                    return "response_too_large", None, used
            return "ok", json.loads(body), used
    except (requests.RequestException, ValueError, RecursionError):
        return "transport_or_decode_failure", None, used


def _collect(filters, api_key):
    payload = {"filters": filters, "fields": FIELDS, "limit": PAGE_SIZE,
               "sorts": [{"field": "crustdata_person_id", "order": "asc"}]}
    histories, steps, cursors, charges = {}, [], set(), []
    read_page = False
    expected = None
    for page in range(1, MAX_PAGES + 1):
        status, data, used = _search_page(payload, api_key)
        charges.append(used)
        step = {"name": "person_search", "detail": f"Estate search page {page}", "status": status,
                "credits": float(used) if used is not None else None}
        steps.append(step)
        if status != "ok":
            break
        if (not isinstance(data, dict) or not isinstance(data.get("profiles"), list)
                or len(data["profiles"]) > PAGE_SIZE):
            step["status"] = "invalid_page"
            break
        read_page = True
        for profile in data["profiles"]:
            pid = _id(profile.get("crustdata_person_id")) if isinstance(profile, dict) else None
            if pid is None:
                step["status"] = "incomplete_page"
                continue
            roles, complete = _history(profile)
            if pid in histories and histories[pid] != (roles, complete):
                roles |= histories[pid][0]
                complete = False
            histories[pid] = roles, complete
        total, cursor = data.get("total_count"), data.get("next_cursor")
        if type(total) is not int or total < 0 or "next_cursor" not in data:
            step["status"] = "incomplete_page"
        elif expected is not None and expected != total:
            step["status"] = "total_changed"
        elif cursor is None:
            if total != len(histories) or data.get("total_count_relation") == "gte":
                step["status"] = "incomplete_page"
            break
        elif not isinstance(cursor, str) or not cursor or cursor in cursors or not data["profiles"]:
            step["status"] = "invalid_cursor"
        elif page == MAX_PAGES:
            step["status"] = "page_limit"
        if step["status"] != "ok":
            break
        expected = total
        cursors.add(cursor)
        payload = {**payload, "cursor": cursor}
    credits = float(sum(charges)) if all(c is not None for c in charges) else None
    return histories if read_page else None, steps, credits


def estate_evidence(subject, domain, resolved_company, bankruptcy_date, as_of) -> dict:
    """Collect one display-safe estate observation. See docs/discussion/estate.md."""
    cid, domains = _identity(resolved_company, domain)
    filing, cutoff = _day(bankruptcy_date), _day(as_of)
    api_key = os.getenv("CRUSTDATA_API_KEY")
    flows, steps = [], []
    coverage = unknown = credits = None
    if not cid and not domains:
        status, detail = "unresolved_company", "A resolved estate company ID or verified domain is required."
    elif not filing or not cutoff or not filing <= cutoff <= datetime.now(timezone.utc).date():
        status, detail = "invalid_window", "The filing date and cutoff must form a historical date range."
    elif not api_key:
        status, detail = "unavailable", "Crustdata person search is unavailable."
    else:
        field = "company_id" if cid else "company_website_domain"
        filters = {"field": f"{EMPLOYMENT}.{field}", "type": "=", "value": cid or domains[0]}
        histories, steps, credits = _collect(filters, api_key)
        complete = steps[-1]["status"] == "ok"
        if histories is not None:
            coverage, unknown, flows = _aggregate(histories, cid, domains, filing, cutoff, complete)
        if histories is None:
            status, detail = "unavailable", "No usable Crustdata search page was received."
        elif not complete:
            status, detail = "partial", "Search interrupted. Destination totals are withheld."
            unknown, flows = None, []
        elif coverage is None:
            status, detail = "unresolved_company", "The employer domain maps to multiple company IDs."
        elif coverage < MIN_COVERAGE:
            status, detail = "insufficient_coverage", f"Insufficient witnesses. At least {MIN_COVERAGE} profiles are required."
            unknown = None
        else:
            status = "ok"
            detail = f"Retrospective reconstruction of next-employer starts from {filing} through {cutoff}."
            detail += (f" Showing destinations with at least {MIN_GROUP} people." if flows
                       else " No destination met the date and group-size requirements.")
            if unknown:
                detail += f" {unknown} profiles have no published destination."
        if coverage is not None:
            detail += f" Reviewed {coverage} distinct estate profiles."
    observed = datetime.now(timezone.utc).isoformat()
    evidence = [{"label": "Estate employee flows", "source": "crustdata", "url": SEARCH_URL,
                 "as_of": observed, "mode": "LIVE", "detail": detail, "status": status}]
    steps.append({"name": "Estate employee flows", "status": status, "detail": detail})
    return {"evidence": evidence, "steps": steps, "flows": flows, "credits": credits, "signals": [], "as_of": observed,
            "status": status, "coverage": coverage, "unknown": unknown}
