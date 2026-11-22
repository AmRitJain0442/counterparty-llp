"""Interpret live provider responses without retaining their private payloads.

The caller collects consent and resolves the intake identifiers. Retrieval time
dates a card. A filing date, role start or headcount point dates an observation.
"""
import json
import re
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
    end = max(r.end for r in vendor)
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
            detail += f" {label}: {value}."
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
    charges = [_credits(_dict(c).get("actual")) for c in _list(raw.get("credits"))]
    return dict(evidence=review.evidence, signals=review.signals, steps=review.steps, flows=[],
                credits=float(sum(charges)) if charges and all(c is not None for c in charges) else None)
