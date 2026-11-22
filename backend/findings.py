"""Interpret live provider responses without retaining their private payloads.

The caller collects consent and resolves the intake identifiers. Retrieval time
dates a card. A filing date, role start or headcount point dates an observation.
"""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .estate import MIN_COVERAGE, MIN_GROUP, Period, _credits, _day, _domain, _history, _identity, _role_date
from .providers import OPERATIONS


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _name(value):
    return " ".join(re.findall(r"[^\W_]+", value.casefold())) if isinstance(value, str) else ""


def _issuer_name(value):
    # Accept common punctuation/legal-suffix variants, never a substring match.
    return re.sub(r" (?:incorporated|inc|corporation|corp|ltd|limited|plc|as)$", "", _name(value))


def _cik(value):
    value = str(value)
    if re.fullmatch(r"[0-9]{1,10}", value) and int(value):
        return value.zfill(10)
    return None


def _profile_key(value):
    if isinstance(value, str):
        match = re.fullmatch(r"https://(?:www\.)?linkedin\.com/in/([A-Za-z0-9_%\-]+)/?", value, re.I)
        if match:
            return match[1].casefold()
    return None


def _retrieved(row):
    value = row.get("as_of")
    if _day(value) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    return None


PUBLIC_SOURCES = {
    "submissions": ("sec", "https://www.sec.gov/edgar/search/"),
    "rdap": ("rdap", "https://lookup.icann.org/"),
    "ifsc": ("ifsc", "https://ifsc.razorpay.com/"),
    "openiban": ("openiban", "https://openiban.com/"),
    "brreg": ("brreg", "https://data.brreg.no/enhetsregisteret/api/enheter"),
    "brreg_roles": ("brreg_roles", "https://data.brreg.no/enhetsregisteret/api/enheter"),
    "gleif": ("gleif", "https://www.gleif.org/"),
    "crtsh": ("crtsh", "https://crt.sh/"),
    "wayback": ("wayback", "https://web.archive.org/"),
}
SOURCES = {op: ("crustdata", "https://api.crustdata.com" + path) for op, path in OPERATIONS.items()}
SOURCES.update(PUBLIC_SOURCES)


def _known(row):
    return (isinstance(row, dict) and isinstance(row.get("operation"), str)
            and row["operation"] in SOURCES and SOURCES[row["operation"]][0] == row.get("provider"))


def _status(value):
    if isinstance(value, str) and (value in {"ok", "unavailable", "rate_limited", "response_too_large",
                                             "transport_or_decode_failure", "scope_required", "skipped"}
                                   or re.fullmatch(r"http_[1-5][0-9]{2}", value)):
        return value
    return "unknown"


class _Review:
    def __init__(self, raw):
        self.evidence = []
        self.signals = []
        self.steps = []
        self.rows = {}
        for step in _list(raw.get("steps")):
            if _known(step):
                self.step(step["operation"], _status(step.get("status")), "Provider collection")
        for row in _list(raw.get("evidence")):
            if _known(row) and row.get("status") == "ok":
                self.rows.setdefault(row["operation"], []).append(row)

    def one(self, operation):
        rows = self.rows.get(operation, [])
        return rows[0] if len(rows) == 1 else {}

    def step(self, name, status, detail):
        self.steps.append(dict(name=name, status=status, detail=detail))

    def card(self, row, label, detail, *, observed=None, url=None):
        op = row["operation"]
        # Providers allocate IDs per lane. Allocate public IDs after collection.
        card = dict(id=f"live-{len(self.evidence) + 1}", source=row["provider"], operation=op,
                    label=label, detail=detail, mode="LIVE", as_of=_retrieved(row),
                    url=url or SOURCES[op][1], status="ok")
        if observed:
            card["observed_on"] = observed.isoformat()
        self.evidence.append(card)
        return card


def _match(row, kind):
    data = row.get("data")
    if not isinstance(data, list) or len(data) != 1:
        return {}, {}
    envelope = _dict(data[0])
    if envelope.get("match_status", "matched") != "matched":
        return {}, {}
    matches = [m for m in _list(envelope.get("matches")) if isinstance(m, dict)
               and type(m.get("confidence_score")) in (int, float) and .8 <= m["confidence_score"] <= 1]
    if len(matches) != 1:
        return {}, {}
    return envelope, _dict(matches[0].get(kind + "_data"))


def _issuer_subject(sec, subject):
    label = _issuer_name(subject)
    return bool(label and (label == _issuer_name(sec.get("name"))
                           or label in {_name(t) for t in _list(sec.get("tickers"))}
                           or _cik(subject) and _cik(subject) == _cik(sec.get("cik"))))


def _company(review, subject, inputs):
    """Bind enrichment to the unique intake match, including across collection lanes."""
    primary = "company_identify" if review.rows.get("company_identify") else "company_enrich"
    row = review.one(primary)
    env, company = _match(row, "company")
    cid, domains = _identity(company, inputs.get("domain"))
    name = _issuer_name(_dict(company.get("basic_info")).get("name"))
    domain = _domain(inputs.get("domain"))
    sec = _dict(review.one("submissions").get("data"))
    if inputs.get("domain"):
        bound = domain and domain in domains
    else:
        bound = (name and (name == _issuer_name(subject)
                           or (name == _issuer_name(sec.get("name")) and _issuer_subject(sec, subject))))
    kind, echo = env.get("match_type"), env.get("matched_on")
    if kind == "domain":
        bound = bound and _domain(echo) in domains and (not domain or _domain(echo) == domain)
    elif kind == "name":
        bound = bound and _name(echo) == _name(subject)
    elif kind == "crustdata_company_id":
        bound = bound and str(echo) == str(cid)
    if not cid or not bound:
        review.step("Company identity", "unresolved", "A unique company tied to the intake identifier is required.")
        return None, [], "", {}
    review.card(row, "Company identity", "A unique company record matched the intake identifier.")
    if primary == "company_enrich" or not review.rows.get("company_enrich"):
        return cid, domains, name, company if primary == "company_enrich" else {}
    extra = review.one("company_enrich")
    env, enriched = _match(extra, "company")
    other_id, _ = _identity(enriched, None)
    if other_id != cid or (env.get("match_type") == "crustdata_company_id" and str(env.get("matched_on")) != str(cid)):
        review.step("Company enrichment identity", "unresolved", "The enrichment could not be tied to the matched company.")
        return cid, domains, name, {}
    return cid, domains, name, enriched


SEC_ITEMS = {"5.02": "directors, officers or compensation", "4.01": "certifying accountant change"}


def _filings(review, subject, inputs, company_name, domains):
    row = review.one("submissions")
    if not row:
        return
    sec = _dict(row.get("data"))
    cik = _cik(sec.get("cik"))
    bound = _issuer_subject(sec, subject)
    if company_name:
        # A caller can supply both a real CIK and a real, unrelated domain.
        websites = (_domain(sec.get("website")), _domain(sec.get("investorWebsite")))
        same_company = company_name == _issuer_name(sec.get("name")) or bool(set(domains).intersection(websites))
        bound = same_company and (bound or _issuer_name(subject) == company_name or _domain(subject) in domains)
    if not cik or cik != _cik(inputs.get("cik")) or not bound:
        review.step("SEC issuer identity", "unresolved", "The CIK and issuer could not be tied to this company.")
        return
    columns = _dict(_dict(sec.get("filings")).get("recent"))
    latest = {}
    cutoff = _day(row.get("as_of"))
    # filingDate, form and items are parallel SEC arrays. An empty cell belongs
    # to its original filing. Never compact or sort the columns independently.
    for i, (form, items, filing) in enumerate(zip(*(_list(columns.get(k)) for k in ("form", "items", "filingDate")))):
        filed = _day(filing)
        if form not in ("8-K", "8-K/A") or not isinstance(items, str) or not filed or not cutoff or filed > cutoff:
            continue
        for item in SEC_ITEMS.keys() & {s.strip() for s in items.split(",")}:
            if item not in latest or filed > latest[item][0]:
                latest[item] = (filed, i, form)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    for item in SEC_ITEMS:
        if item not in latest:
            continue
        filed, index, form = latest[item]
        detail = f"Form {form} filed {filed} lists Item {item} ({SEC_ITEMS[item]})."
        reports = _list(columns.get("reportDate"))
        report = _day(reports[index]) if index < len(reports) else None
        if report and report <= filed:
            detail += f" The report date is {report}."
        accessions = _list(columns.get("accessionNumber"))
        accession = accessions[index] if index < len(accessions) else None
        link = url
        if isinstance(accession, str) and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"
        review.card(row, f"8-K Item {item}", detail, observed=filed, url=link)
    if not latest:
        review.step("SEC filings", "unknown", "The returned index supplied no dated Item 5.02 or 4.01 filing for review.")


def _person(review, inputs):
    row = review.one("person_enrich")
    env, person = _match(row, "person")
    requested = _profile_key(inputs.get("person_url"))
    if not requested or _profile_key(env.get("matched_on")) != requested:
        review.step("Profile identity", "unresolved", "The requested profile has no unique, confident match.")
        return {}, None, False
    refresh = _day(person.get("updated_at") or _dict(person.get("basic_profile")).get("last_updated"))
    retrieved = _day(row.get("as_of"))
    fresh = bool(retrieved and refresh and timedelta(0) <= retrieved - refresh <= timedelta(days=30))
    if not fresh:
        review.step("Profile freshness", "unknown", "The profile refresh date is missing, old or outside the collection window.")
    cutoff = min(retrieved, refresh) if retrieved and refresh else retrieved
    return person, cutoff, fresh


def _employer(role, cid, domains):
    if role.domain in domains:
        return cid if role.cid in (None, cid) else None
    return role.cid or role.domain


def _next_start(roles, cid, domains, cutoff):
    """Date the first external job after the latest evidenced vendor tenure."""
    vendor = [r for r in roles if _employer(r, cid, domains) == cid]
    if not vendor or any(r.current or not r.end or r.end.last > cutoff for r in vendor):
        return None
    end = Period(max(r.end.first for r in vendor), max(r.end.last for r in vendor))
    # An overlapping, undated or ambiguous intervening role breaks the sequence.
    after = [r for r in roles if r not in vendor and (not r.end or r.end.last >= end.first)
             and (not r.start or r.start.first <= cutoff)]
    if not after or any(not r.start for r in after):
        return None
    earliest = min(r.start.last for r in after)
    first = [r for r in after if r.start.first <= earliest]
    destinations = {_employer(r, cid, domains) for r in first}
    start = Period(min(r.start.first for r in first), earliest)
    if (None in destinations or len(destinations) != 1 or start.first < end.last or start.last > cutoff
            or any(r.start and r.start.last >= start.first for r in vendor)):
        return None
    return start


def _period_text(period):
    return str(period.first) if period.first == period.last else f"{period.first} through {period.last}"


def _sending_domain(review, inputs, domains):
    row = review.one("rdap")
    if not row:
        return None
    record = _dict(row.get("data"))
    sender = inputs.get("sender_domain") or inputs.get("domain")
    ldh = record.get("ldhName")
    if (not isinstance(sender, str) or not isinstance(ldh, str) or not _domain(ldh)
            or ldh.rstrip(".").casefold() != sender.rstrip(".").casefold()
            or record.get("objectClassName", "domain") != "domain"):
        review.step("Sender domain identity", "unresolved", "The RDAP record could not be tied to the queried domain.")
        return None
    dates = {_day(e.get("eventDate")) for e in _list(record.get("events"))
             if isinstance(e, dict) and e.get("eventAction") == "registration"}
    retrieved = _day(row.get("as_of"))
    if len(dates) != 1:
        return None
    registered = dates.pop()
    if not registered or not retrieved or registered > retrieved:
        return None
    age = (retrieved - registered).days
    detail = f"RDAP records registration on {registered}, {age} days before collection."
    card = review.card(row, "Domain registration", detail, observed=registered)
    # The registered domain and the vendor's published domain have different
    # roles in a payment inquiry. A vendor's own recent domain is context.
    if inputs.get("sender_domain") and domains and _domain(sender) not in domains and age <= 30:
        return card
    return None


def _bank(review, inputs):
    row = review.one("ifsc")
    data = _dict(row.get("data"))
    code = inputs.get("ifsc")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", code) or data.get("IFSC") != code:
        return
    detail = f"The submitted IFSC identifies bank code {code[:4]}."
    for key, label in (("BANK", "Bank"), ("CITY", "City")):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r"[^\W\d_][\w .,&'()-]{0,80}", value):
            detail += f" {label} listed as {value}."
    review.card(row, "Bank branch lookup", detail + " Account ownership requires independent confirmation.")


def _payment(review, inputs, cid, domains, consent):
    _sending_domain(review, inputs, domains)
    _bank(review, inputs)
    if not cid or not consent or not inputs.get("person_url"):
        return
    person, cutoff, fresh = _person(review, inputs)
    roles, complete = _history(person)
    start = _next_start(roles, cid, domains, cutoff) if complete and cutoff else None
    if not start:
        review.step("Vendor employment transition", "unknown",
                    "No ordered, dated next-employer start was established for this vendor.")
        return
    detail = f"The matched profile records a subsequent external employer start on {_period_text(start)}."
    if not fresh:
        detail += " Current affiliation requires a refreshed record."
    card = review.card(review.one("person_enrich"), "Next-employer start", detail,
                       observed=start.first if start.first == start.last else None)
    if start.first != start.last:
        card.update(observed_from=str(start.first), observed_through=str(start.last))


@dataclass(frozen=True)
class _Claim:
    window: Period | None
    headcount: int | None
    department: str | None


ISO_PART = r"[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?"
DATE_RANGE = re.compile(rf"\b({ISO_PART})\s*(?:to|through|until|[-–—])\s*({ISO_PART})\b", re.I)
TEAM = re.compile(r"\b(?:led|managed|supervised|headed)\s+(?:a\s+team\s+of\s+)?([0-9]+)\s+"
                  r"(engineers?|finance staff|employees?|people|staff|direct reports?)\b", re.I)
FUNCTIONS = {"engineering": "Engineering", "engineer": "Engineering", "engineers": "Engineering",
             "finance": "Finance", "finance staff": "Finance", "sales": "Sales", "marketing": "Marketing",
             "operations": "Operations", "product management": "Product Management"}


def _candidate_claim(inputs):
    """Accept structured claim fields or the date range and team size in the intake text."""
    claim = inputs.get("claim", "")
    if isinstance(claim, str) and claim.lstrip().startswith("{"):
        try:
            claim = json.loads(claim)
        except (ValueError, RecursionError):
            return None
    fields = _dict(claim)
    start = inputs.get("claim_start", fields.get("start_date"))
    end = inputs.get("claim_end", fields.get("end_date"))
    count = inputs.get("claim_headcount", fields.get("headcount"))
    department = inputs.get("claim_department", fields.get("department"))
    if isinstance(claim, str):
        ranges = DATE_RANGE.findall(claim)
        teams = TEAM.findall(claim)
        if len(ranges) > 1 or len(teams) > 1:
            return None
        if ranges and start is None and end is None:
            start, end = ranges[0]
        if teams and count is None:
            count, department = teams[0]
        if start is None and end is None:
            quarter = re.search(r"\bQ([1-4])\s+([0-9]{4})\b", claim, re.I)
            if quarter:
                last_month = 3 * int(quarter[1])
                start, end = f"{quarter[2]}-{last_month - 2:02}", f"{quarter[2]}-{last_month:02}"
    window = None
    if start is not None or end is not None:
        first, _ = _role_date(start if start is not None else end)
        last, _ = _role_date(end if end is not None else start)
        if not first or not last or first.first > last.last:
            return None
        window = Period(first.first, last.last)
    if count is not None:
        if not re.fullmatch(r"[0-9]{1,8}", str(count)):
            return None
        count = int(count)
    group = _name(department)
    if group and group not in FUNCTIONS and group not in {
        "employee", "employees", "people", "staff", "direct report", "direct reports", "total"
    }:
        return None
    return _Claim(window, count, FUNCTIONS.get(group))


def _ranges(roles, cid, domains, cutoff):
    """Guaranteed overlap uses the latest possible start and earliest possible end."""
    spans = []
    for role in roles:
        if _employer(role, cid, domains) != cid or not role.start:
            continue
        end = role.end or role.start  # An open role supplies only its dated start.
        if role.start.last <= end.first <= end.last <= cutoff:
            spans.append(Period(role.start.last, end.first))
    merged = []
    for span in sorted(spans):
        if merged and (span.first - merged[-1].last).days <= 1:
            merged[-1] = Period(merged[-1].first, max(span.last, merged[-1].last))
        else:
            merged.append(span)
    return merged


def _intersects(a, b):
    return max(a.first, b.first) <= min(a.last, b.last)


def _employment_dates(review, reference, claim):
    if not reference:
        review.step("Claimed employment dates", "unknown", "No dated role at the matched employer could be compared.")
        return []
    if not claim.window:
        detail = f"The profile records employment at the matched company on {_period_text(reference[-1])}."
        review.card(review.one("person_enrich"), "Dated employment", detail)
        return reference
    window = claim.window
    overlap = [Period(max(s.first, window.first), min(s.last, window.last)) for s in reference if _intersects(s, window)]
    prefix = f"The claim covers {_period_text(window)}. "
    if window in overlap:
        detail = prefix + "The dated role history covers the claimed period."
    elif overlap:
        detail = prefix + f"The dated role history overlaps part of the claim, including {_period_text(overlap[-1])}."
    else:
        closest = min(reference, key=lambda s: max(window.first - s.last, s.first - window.last))
        detail = prefix + f"No documented overlap. The closest recorded interval is {_period_text(closest)}."
    review.card(review.one("person_enrich"), "Claimed employment dates", detail)
    return overlap


def _colleagues(review, target, reference, cid, domains):
    rows = review.rows.get("person_search", [])
    pid = target.get("crustdata_person_id")
    if not reference or not rows or type(pid) is not int or pid <= 0:
        return
    peers = {}
    for row in rows:
        cutoff = _day(row.get("as_of"))
        if not cutoff:
            continue
        for peer in _list(_dict(row.get("data")).get("profiles")):
            peer = _dict(peer)
            other = peer.get("crustdata_person_id")
            if type(other) is not int or other <= 0 or other == pid:
                continue
            roles, _ = _history(peer)
            if not any(_employer(r, cid, domains) == cid for r in roles):
                continue
            refreshed = _day(peer.get("updated_at"))
            spans = _ranges(roles, cid, domains, min(cutoff, refreshed) if refreshed else cutoff)
            if other in peers and spans != peers[other]:
                peers[other] = []  # Conflicting duplicate profiles supply no overlap.
            else:
                peers[other] = spans
    count = sum(any(_intersects(a, b) for a in spans for b in reference) for spans in peers.values())
    if len(peers) < MIN_COVERAGE or count < MIN_GROUP:
        review.step("Colleague overlap", "insufficient_coverage", "Insufficient dated peer coverage to publish an aggregate.")
        return
    review.card(rows[-1], "Colleague overlap",
                f"{count} distinct colleagues in the returned sample overlap the matched profile at this employer "
                "within the reviewed dates. These records share one provider.")


def _headcounts(company, department, cutoff):
    """Return actual dated estimates for one population, excluding conflicting points."""
    headcount = _dict(company.get("headcount"))
    series = headcount.get("timeseries")
    current = headcount.get("total")
    if department:
        functions = _dict(_dict(headcount.get("by_function_timeseries")).get("CURRENT_FUNCTION"))
        series = next((v for k, v in functions.items() if _name(k) == _name(department)), None)
        current = next((v for k, v in _dict(headcount.get("by_role_absolute")).items()
                        if _name(k) == _name(department)), None)
    points = {}
    for point in [*_list(series), {"date": company.get("updated_at"), "employee_count": current}]:
        day = _day(_dict(point).get("date"))
        size = _dict(point).get("employee_count")
        if cutoff and day and day <= cutoff and type(size) is int and size >= 0:
            points.setdefault(day, set()).add(size)
    return sorted((d, next(iter(s))) for d, s in points.items() if len(s) == 1)


def _claim_headcount(review, company, claim):
    row = review.one("company_enrich")
    population = claim.department or "whole-company"
    count = claim.headcount
    claimed = str(count) if count >= MIN_GROUP else "fewer than five"
    detail = f"The claim lists {claimed} staff. "
    candidates = _headcounts(company, claim.department, _day(row.get("as_of")))
    if claim.window:
        candidates = [(d, s) for d, s in candidates if claim.window.first <= d <= claim.window.last]
    if not candidates or candidates[-1][1] < MIN_GROUP:
        review.step("Claimed headcount", "unknown", detail + f"No publishable dated {population} estimate for comparison.")
        return
    day, size = candidates[-1]
    detail += f"The {population} estimate on {day} was {size} profiles. "
    if claim.window:
        relation = "below" if size < count else "at or above"
        detail += f"At this point in the claimed period, the estimate was {relation} the claimed size."
    else:
        detail += "The claim needs a date to establish whether the periods match."
    review.card(row, "Claimed headcount", detail + " Reporting lines require separate evidence.", observed=day)


def _candidate(review, inputs, cid, domains, company, consent):
    if not consent or not cid:
        return
    claim = _candidate_claim(inputs)
    if claim is None:
        review.step("Candidate claim", "unknown", "The claim has invalid or ambiguous dates, team size or function.")
        return
    if claim.headcount is not None:
        _claim_headcount(review, company, claim)
    person, cutoff, _ = _person(review, inputs)
    if not person or not cutoff:
        return
    roles, _ = _history(person)
    dates = _employment_dates(review, _ranges(roles, cid, domains, cutoff), claim)
    _colleagues(review, person, dates, cid, domains)
    if not claim.window and claim.headcount is None:
        review.step("Candidate claim", "unknown", "A reviewer needs a dated or quantitative claim to compare.")


def interpret(desk, subject, inputs, raw):
    """Project one run_live response (or its joined lanes) into ledger-safe findings."""
    inputs, raw = _dict(inputs), _dict(raw)
    review = _Review(raw)
    cid, domains, company_name, company = _company(review, subject, inputs)
    if desk == "company":
        _filings(review, subject, inputs, company_name, domains)
    consent = inputs.get("consent") is not False and not any(
        _dict(s).get("type") == "consent_required" for s in _list(raw.get("signals")))
    if not consent:
        review.step("Profile consent", "skipped", "Profile evidence requires consent.")
    if desk == "payment":
        _payment(review, inputs, cid, domains, consent)
    elif desk == "candidate":
        _candidate(review, inputs, cid, domains, company, consent)
    charges = [_credits(_dict(c).get("actual")) for c in _list(raw.get("credits"))]
    return dict(evidence=review.evidence, signals=review.signals, steps=review.steps, flows=[],
                credits=float(sum(charges)) if charges and all(c is not None for c in charges) else None)
