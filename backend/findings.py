"""Interpret live provider responses without retaining their private payloads.

The caller collects consent and resolves the intake identifiers. Retrieval time
dates a card. A filing date, role start or headcount point dates an observation.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .estate import MIN_COVERAGE, MIN_GROUP, Period, _credits, _day, _domain, _history, _identity, _role_date
from .forecast import forecast_window
from .providers import OPERATIONS
from .vendor import vendor_records


INDEX_MAX_AGE = timedelta(days=30)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _name(value):
    return " ".join(re.findall(r"[^\W_]+", value.casefold())) if isinstance(value, str) else ""


def _issuer_name(value):
    # Accept common punctuation/legal-suffix variants, never a substring match.
    if isinstance(value, str):
        # Public company profiles may append an accelerator batch to the legal name.
        value = re.sub(r"\s*\(YC [WSFX]\d{2}\)\s*$", "", value, flags=re.I)
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
        if len(value) == 10:
            return value
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    return None


def _input_domain(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9.-]{1,254}", value):
        return _domain(value)
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
        self.proposition = None
        for step in _list(raw.get("steps")):
            if _known(step):
                self.step(step["operation"], _status(step.get("status")), "Provider collection")
        if raw.get("mode", "live") not in ("live", "LIVE"):
            return
        for row in _list(raw.get("evidence")):
            if (_known(row) and row.get("status") == "ok" and _retrieved(row)
                    and row.get("mode", "LIVE") == "LIVE"):
                self.rows.setdefault(row["operation"], []).append(row)

    def one(self, operation):
        rows = self.rows.get(operation, [])
        return rows[0] if len(rows) == 1 else {}

    def step(self, name, status, detail):
        self.steps.append(dict(name=name, status=status, detail=detail))

    def card(self, row, label, detail, *, observed=None, url=None):
        op = row["operation"]
        # Providers allocate IDs per lane. Allocate public IDs after collection.
        provider = row["provider"]
        card = dict(id=f"live-{len(self.evidence) + 1}", source="Crustdata" if provider == "crustdata" else provider,
                    provider=provider, operation=op,
                    label=label, detail=detail, mode="LIVE", as_of=_retrieved(row),
                    url=url or SOURCES[op][1], status="ok")
        if observed:
            card["observed_on"] = observed.isoformat()
        self.evidence.append(card)
        return card

    def observe(self, card, claim, *, primary=False):
        """Only an observed fact can cite a card at the proposition gate."""
        if not card["as_of"]:
            return
        card["claim"] = claim
        self.signals.append(dict(type="claim_observation", claim=claim, evidence_id=card["id"],
                                 provider=card["provider"], operation=card["operation"], status="ok"))
        if primary and self.proposition is None:
            self.proposition = claim


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


def _company(review, desk, subject, inputs):
    """Bind enrichment to the unique intake match, including across collection lanes."""
    primary = "company_identify" if review.rows.get("company_identify") else "company_enrich"
    row = review.one(primary)
    env, company = _match(row, "company")
    cid, domains = _identity(company, inputs.get("domain"))
    name = _issuer_name(_dict(company.get("basic_info")).get("name"))
    domain = _input_domain(inputs.get("domain"))
    sec = _dict(review.one("submissions").get("data"))
    named = name and name == _issuer_name(subject)
    if desk == "company" and domain in domains and name:
        # A verified domain anchors spacing variants such as "SkanAI" and "Skan AI".
        named = named or name.replace(" ", "") == _issuer_name(subject).replace(" ", "")
    ticker = (name and name == _issuer_name(sec.get("name")) and _cik(sec.get("cik"))
              and _cik(sec["cik"]) == _cik(inputs.get("cik")) and _issuer_subject(sec, subject))
    if inputs.get("domain"):
        bound = domain and domain in domains
        if desk == "company":
            bound = bound and (named or ticker or _input_domain(subject) in domains)
    else:
        bound = named or ticker
    kind, echo = env.get("match_type"), env.get("matched_on")
    if kind == "domain":
        bound = bound and _domain(echo) in domains and (not domain or _domain(echo) == domain)
    elif kind == "name":
        bound = bound and _name(echo) == _name(subject)
    elif kind == "crustdata_company_id":
        bound = bound and str(echo) == str(cid)
    elif kind is not None:
        bound = False
    if not cid or not bound:
        status = "unresolved" if review.rows.get(primary) else "unknown"
        detail = "A unique company tied to the intake identifier is required."
        if desk == "company" and company and not named:
            matched_name = _dict(company.get("basic_info")).get("name")
            detail = (f"Crustdata returned {matched_name or 'a company'}, but it could not be matched to the company subject. "
                      "Enter the company's name or domain as the subject. For a leadership check, use the separate executive fields.")
        review.step("Company identity", status, detail)
        return None, [], "", {}
    review.card(row, "Company identity", "A unique company record matched the intake identifier.")
    if primary == "company_enrich" or not review.rows.get("company_enrich"):
        return cid, domains, name, company if primary == "company_enrich" else {}
    extra = review.one("company_enrich")
    env, enriched = _match(extra, "company")
    other_id, other_domains = _identity(enriched, None)
    domain_conflict = domains and other_domains and set(domains).isdisjoint(other_domains)
    wrong_echo = env.get("match_type") == "crustdata_company_id" and str(env.get("matched_on")) != str(cid)
    if other_id != cid or wrong_echo or domain_conflict:
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
        website = _domain(sec.get("website"))
        same_company = website in domains if website and domains else company_name == _issuer_name(sec.get("name"))
        bound = same_company and (bound or _issuer_name(subject) == company_name or _domain(subject) in domains)
    if not cik or cik != _cik(inputs.get("cik")) or not bound:
        review.step("SEC issuer identity", "unresolved", "The CIK and issuer could not be tied to this company.")
        return
    columns = _dict(_dict(sec.get("filings")).get("recent"))
    forms, items_column, dates = (_list(columns.get(k)) for k in ("form", "items", "filingDate"))
    if not len(forms) == len(items_column) == len(dates):
        review.step("SEC filings", "unknown", "The filing index columns have inconsistent lengths.")
        return
    latest = {}
    cutoff = _day(row.get("as_of"))
    # filingDate, form and items are parallel SEC arrays. An empty cell belongs
    # to its original filing. Never compact or sort the columns independently.
    for i, (form, items, filing) in enumerate(zip(forms, items_column, dates)):
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
        report = _day(reports[index]) if len(reports) == len(forms) else None
        if report and report <= filed:
            detail += f" The report date is {report}."
        accessions = _list(columns.get("accessionNumber"))
        accession = accessions[index] if len(accessions) == len(forms) else None
        link = url
        if isinstance(accession, str) and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"
        card = review.card(row, f"8-K Item {item}", detail, observed=filed, url=link)
        review.observe(card, f"CIK {cik} filed {form} Item {item} on {filed}.", primary=True)
    if not latest:
        review.step("SEC filings", "unknown", "The returned index supplied no dated Item 5.02 or 4.01 filing for review.")


def _person(review, inputs):
    row = review.one("person_enrich")
    env, person = _match(row, "person")
    requested = _profile_key(inputs.get("person_url"))
    bound = (person and requested and _profile_key(env.get("matched_on")) == requested
             and env.get("match_type", "professional_network_profile_url") == "professional_network_profile_url")
    if review.rows.get("person_identify"):
        identity_env, identity = _match(review.one("person_identify"), "person")
        pid = identity.get("crustdata_person_id")
        bound = (bound and _profile_key(identity_env.get("matched_on")) == requested
                 and identity_env.get("match_type", "professional_network_profile_url") == "professional_network_profile_url"
                 and type(pid) is int and pid > 0 and type(person.get("crustdata_person_id")) is int
                 and pid == person["crustdata_person_id"])
    if not bound:
        status = "unresolved" if review.rows.get("person_enrich") else "unknown"
        review.step("Profile identity", status, "The requested profile has no unique, confident match.")
        return {}, None, False
    refresh = _day(person.get("updated_at") or _dict(person.get("basic_profile")).get("last_updated"))
    retrieved = _day(row.get("as_of"))
    fresh = bool(retrieved and refresh and timedelta(0) <= retrieved - refresh <= INDEX_MAX_AGE)
    if not fresh:
        detail = (f"The profile refresh on {refresh} falls outside the 30-day window ending {retrieved}."
                  if refresh and retrieved else "The profile has no usable refresh date.")
        review.step("Profile freshness", "unknown", detail + " Current affiliation remains unknown.")
    cutoff = min(retrieved, refresh) if retrieved and refresh else retrieved
    return person, cutoff, fresh


def _employer(role, cid, domains):
    if role.domain in domains:
        return cid if role.cid in (None, cid) else None
    if role.cid == cid and role.domain and domains:
        return None
    return role.cid or role.domain


def _next_start(roles, cid, domains, cutoff):
    """Date the first external job after the latest evidenced vendor tenure."""
    vendor = {r for r in roles if _employer(r, cid, domains) == cid}
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
            or not re.fullmatch(r"[A-Za-z0-9.-]{1,254}", ldh)
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
    card = review.card(row, "Domain registration", detail, observed=registered,
                       url=f"https://lookup.icann.org/en/lookup?name={ldh.rstrip('.').lower()}")
    # The registered domain and the vendor's published domain have different
    # roles in a payment inquiry. A vendor's own recent domain is context.
    if inputs.get("sender_domain") and domains and _domain(sender) not in domains and age <= 30:
        review.observe(card, f"The sending domain was registered on {registered}.")


def _bank(review, inputs):
    iban = inputs.get("iban")
    validation = review.one("openiban")
    bank_data = _dict(validation.get("data"))
    if (isinstance(iban, str) and re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}", iban)
            and bank_data.get("iban") == iban and type(bank_data.get("valid")) is bool):
        outcome = "passed" if bank_data["valid"] else "failed"
        review.card(validation, "IBAN validation",
                    f"The submitted IBAN {outcome} the provider's validation checks. Beneficiary ownership requires a callback.")
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
    review.card(row, "Bank branch lookup", detail + " Account ownership requires independent confirmation.",
                url=f"https://ifsc.razorpay.com/{code}")


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
    if fresh:
        review.observe(card, f"The matched contact started a subsequent external job on {_period_text(start)}.",
                       primary=True)


def _vendor_domain(review, inputs, domains):
    """Only matching, independent records can carry the live callback proposition."""
    identify, registry = review.one("company_identify"), review.one("brreg")
    if not identify or not registry or any(s["status"] == "unresolved" for s in review.steps):
        return
    sender, vendor = _input_domain(inputs.get("sender_domain")), _input_domain(inputs.get("domain"))
    if not sender or vendor not in domains or any(sender == d or sender.endswith("." + d) for d in domains):
        return
    org = inputs.get("orgnr")
    record = _dict(registry.get("data"))
    if not isinstance(org, str) or not re.fullmatch(r"[0-9]{9}", org):
        return
    if record.get("organisasjonsnummer") != org:
        review.step("Vendor registry identity", "unresolved", "The returned registry number differs from the intake.")
        return
    if not _domain(record.get("hjemmeside")) or not _issuer_name(record.get("navn")):
        return
    _, company = _match(identify, "company")
    basic = _dict(company.get("basic_info"))
    company_domain = _domain(basic.get("primary_domain"))
    if not company_domain or not _issuer_name(basic.get("name")):
        return
    # The two observations describe the records returned during this inquiry.
    # A markedly older lookup or indexed profile cannot establish the current pair.
    observed = [_day(row.get("as_of")) for row in (identify, registry)]
    refreshed = _day(company.get("updated_at"))
    old_profile = company.get("updated_at") and (not refreshed or not timedelta(0) <= observed[0] - refreshed <= INDEX_MAX_AGE)
    if max(observed) - min(observed) > INDEX_MAX_AGE or old_profile:
        return
    rows = [{**identify, "source": SOURCES["company_identify"][1]},
            {**registry, "source": f"{SOURCES['brreg'][1]}/{org}"}]
    cards = vendor_records({"domain": vendor, "sender_domain": sender, "orgnr": org},
                           {"basic_info": {"name": basic["name"], "primary_domain": company_domain}}, rows)
    if not cards:
        review.step("Vendor registry identity", "unresolved", "The registry and company profile could not confirm the same vendor domain.")
        return
    for card, row in zip(cards, rows):
        card.update(provider=row["provider"], status="ok", operation=row["operation"])
        review.evidence.append(card)
        review.observe(card, card["claim"])
    review.proposition = cards[0]["claim"]


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


def _candidate_claim(inputs, domains, company_name):
    """Accept structured claim fields or the date range and team size in the intake text."""
    claim = inputs.get("claim", "")
    if isinstance(claim, str) and claim.lstrip().startswith("{"):
        try:
            claim = json.loads(claim)
        except (ValueError, RecursionError):
            return None
    fields = _dict(claim)
    if "employer_domain" in fields and _input_domain(fields["employer_domain"]) not in domains:
        return None
    if "employer" in fields and _issuer_name(fields["employer"]) != company_name:
        return None
    start = inputs.get("claim_start", fields.get("start_date"))
    end = inputs.get("claim_end", fields.get("end_date"))
    count = inputs.get("claim_headcount", fields.get("headcount"))
    department = inputs.get("claim_department", fields.get("department"))
    if isinstance(claim, str):
        ranges = DATE_RANGE.findall(claim)
        teams = TEAM.findall(claim)
        if len(ranges) > 1 or len(teams) > 1 or (teams and re.search(r"\b(?:not|never|didn['’]t)\b", claim, re.I)):
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
    if department is not None and not isinstance(department, str):
        return None
    group = _name(department)
    if group in {"employee", "employees", "people", "staff", "direct report", "direct reports", "total"}:
        group = ""
    return _Claim(window, count, FUNCTIONS.get(group, group) or None)


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


def _employment_dates(review, reference, claim, fresh):
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
        covering = next(s for s in reference if s.first <= window.first and window.last <= s.last)
        detail = prefix + f"The recorded interval of {_period_text(covering)} covers the claimed period."
    elif overlap:
        detail = prefix + f"The dated role history overlaps part of the claim, including {_period_text(overlap[-1])}."
    else:
        closest = min(reference, key=lambda s: max(window.first - s.last, s.first - window.last))
        detail = prefix + f"No documented overlap. The closest recorded interval is {_period_text(closest)}."
    card = review.card(review.one("person_enrich"), "Claimed employment dates", detail)
    if fresh and window in overlap:
        review.observe(card, f"The matched profile records employment throughout {_period_text(window)}.", primary=True)
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
    if department:
        functions = _dict(_dict(headcount.get("by_function_timeseries")).get("CURRENT_FUNCTION"))
        series = next((v for k, v in functions.items() if _name(k) == _name(department)), None)
    points = {}
    for point in _list(series):
        day = _day(_dict(point).get("date"))
        size = _dict(point).get("employee_count")
        if cutoff and day and day <= cutoff and type(size) is int and size >= 0:
            points.setdefault(day, set()).add(size)
    return sorted((d, next(iter(s))) for d, s in points.items() if len(s) == 1)


def _claim_headcount(review, company, claim):
    row = review.one("company_enrich")
    population = FUNCTIONS.get(_name(claim.department), "claimed function") if claim.department else "whole-company"
    count = claim.headcount
    claimed = str(count) if count >= MIN_GROUP else "fewer than five"
    detail = f"The claim lists {claimed} staff. "
    candidates = _headcounts(company, claim.department, _day(row.get("as_of")))
    if claim.window:
        candidates = [(d, s) for d, s in candidates if claim.window.first <= d <= claim.window.last]
    else:
        headcount = _dict(company.get("headcount"))
        current = headcount.get("total")
        if claim.department:
            current = next((v for k, v in _dict(headcount.get("by_role_absolute")).items()
                            if _name(k) == _name(claim.department)), None)
        if type(current) is int and current >= MIN_GROUP:
            detail += f"The retrieved profile lists {current} {population} profiles. The claim needs a date for comparison."
            review.card(row, "Claimed headcount", detail)
            return
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
    card = review.card(row, "Claimed headcount", detail + " Reporting lines require separate evidence.", observed=day)
    if claim.window and count >= MIN_GROUP:
        review.observe(card, f"The {population} estimate on {day} was {relation} the claimed size of {count}.", primary=True)


def _candidate(review, inputs, cid, domains, company_name, company, consent):
    if not consent or not cid:
        return
    claim = _candidate_claim(inputs, domains, company_name)
    if claim is None:
        review.step("Candidate claim", "unknown", "The employer, dates, team size or function could not be matched.")
        return
    if claim.headcount is not None:
        _claim_headcount(review, company, claim)
    person, cutoff, fresh = _person(review, inputs)
    if not person or not cutoff:
        return
    roles, _ = _history(person)
    dates = _employment_dates(review, _ranges(roles, cid, domains, cutoff), claim, fresh)
    _colleagues(review, person, dates, cid, domains)
    if not claim.window and claim.headcount is None:
        review.step("Candidate claim", "unknown", "A reviewer needs a dated or quantitative claim to compare.")


def _workforce(review, company):
    row = review.one("company_enrich")
    cutoff = _day(row.get("as_of"))
    for department in (None, "Finance"):
        points = _headcounts(company, department, cutoff)
        if not points or points[-1][1] < MIN_GROUP:
            continue
        population = department or "Whole-company"
        day, count = points[-1]
        observation = f"{population} headcount was estimated at {count} profiles on {day}."
        detail = observation
        if len(points) >= 2 and points[-2][1] >= MIN_GROUP:
            prior, previous = points[-2]
            detail += f" The preceding returned point was {previous} on {prior}."
        card = review.card(row, f"{population} headcount", detail, observed=day)
        review.observe(card, observation, primary=True)


INTERIM_CFO = re.compile(r"(?:interim|acting)\s+(?:(?:group|global)\s+)?(?:cfo|chief financial officer)"
                        r"|(?:cfo|chief financial officer)\s*\((?:interim|acting)\)", re.I)


def executive_titles_match(first, second):
    """Compare exact titles, expanding only standard, unambiguous officer acronyms."""
    aliases = {"ceo": "chief executive officer", "cfo": "chief financial officer", "cto": "chief technology officer",
               "cpo": "chief product officer", "cpto": "chief product and technology officer",
               "coo": "chief operating officer", "cmo": "chief marketing officer", "cro": "chief revenue officer"}
    def normalized(value):
        if not isinstance(value, str):
            return set()
        parts = [_name(part.replace("&", " and ")) for part in re.split(r"[,;|]", value)]
        parts = [p for p in parts if p not in {"founder", "co founder", "cofounder"}]
        return {aliases.get(p, p) for p in parts if p}
    first_roles = normalized(first)
    return bool(first_roles and first_roles == normalized(second))


def _named_leadership(review, company, cid, domains, inputs):
    """A company roster is one provider's report, never independent verification."""
    wanted = _name(inputs.get("executive_name"))
    if not wanted:
        return None

    def unresolved(reason):
        summary = reason + " Confirm the role with a dated statement from the company."
        review.step("Named executive role", "unresolved", summary)
        return {"verdict": "ROLE REVIEW", "summary": summary}

    if not cid or not company:
        return unresolved("The company identity or company enrichment could not be bound to the intake.")
    row = review.one("company_enrich")
    people = _dict(company.get("people"))
    profiles = [_dict(p) for group in ("cxos", "founders", "decision_makers") for p in _list(people.get(group))]
    matches = [p for p in profiles if _name(_dict(p.get("basic_profile")).get("name") or p.get("name")) == wanted]
    if not matches:
        return unresolved("The returned executive roster has no exact name match. Its coverage may be incomplete.")
    ids = {p.get("crustdata_person_id") for p in matches if type(p.get("crustdata_person_id")) is int}
    if (len(ids) != 1 or any(type(p.get("crustdata_person_id")) is not int for p in matches)
            or next(iter(ids), 0) <= 0 or any(p != matches[0] for p in matches[1:])):
        return unresolved("The exact name has ambiguous or conflicting person records in the returned roster.")
    profile = matches[0]
    cutoff = _day(row.get("as_of"))
    refresh = _day(profile.get("updated_at") or _dict(profile.get("basic_profile")).get("last_updated"))
    fresh = bool(cutoff and refresh and timedelta(0) <= cutoff - refresh <= INDEX_MAX_AGE)
    roles = []
    for role in _list(_dict(_dict(profile.get("experience")).get("employment_details")).get("current")):
        role = _dict(role)
        values = role.get("employer_company_id", role.get("crustdata_company_id"))
        employer_ids = {str(v) for v in (values if isinstance(values, list) else [values]) if v is not None}
        if role.get("crustdata_company_id") is not None:
            employer_ids.add(str(role["crustdata_company_id"]))
        sites = role.get("employer_website", [])
        hosts = {_domain(v) for v in (sites if isinstance(sites, list) else [sites])} - {None, ""}
        bound = employer_ids == {str(cid)} if employer_ids else bool(hosts.intersection(domains))
        if not bound or hosts and domains and not hosts.intersection(domains):
            continue
        start, start_valid = _role_date(role.get("employee_start_date") or role.get("start_date"))
        end, end_valid = _role_date(role.get("employee_end_date") or role.get("end_date"))
        title = role.get("employee_title") or role.get("title")
        if (not start_valid or not start or not refresh or not cutoff or start.last > min(refresh, cutoff) or not end_valid or end is not None
                or role.get("is_current") is False or not isinstance(title, str) or not _name(title)):
            return unresolved("The matched person's company role has incomplete or conflicting current-role dates or title.")
        roles.append((title.strip(), start))
    if not roles:
        return unresolved("No dated current role for the exact person could be bound to this company.")
    if len({(_name(t), s) for t, s in roles}) != 1:
        return unresolved("The matched person has conflicting current titles or appointment dates for this company.")
    title, start = roles[0]
    if not fresh:
        detail = (f"Crustdata's employer-bound record lists {title}, starting {_period_text(start)}, "
                  f"with profile refresh on {refresh}. The refresh falls outside the 30-day window ending {cutoff}; "
                  "a current role is not established.")
        review.card(row, "Named executive role", detail, observed=refresh)
        return {**unresolved(detail), "reported_title": title}
    claimed = inputs.get("executive_title")
    company_name = _dict(company.get("basic_info")).get("name") or "the matched company"
    summary = (f"Crustdata lists {inputs['executive_name']} as {title} at {company_name}, with a role start of "
               f"{_period_text(start)} and a profile refresh on {refresh}.")
    review.card(row, "Named executive role", summary, observed=refresh)
    if claimed and not executive_titles_match(claimed, title):
        return {**unresolved(f"{summary} The reported title does not exactly match the submitted title ({claimed})."),
                "reported_title": title}
    summary += " This is one provider's report. A dated statement from the company would provide independent confirmation."
    return {"verdict": "ROLE REPORTED", "summary": summary, "reported_title": title}


def _executives(review, company, cid, domains):
    # Company Enrich embeds PersonProfileEmployer, whose keys differ from
    # Person Enrich. Keep only dated employer roles, never names or biographies.
    row = review.one("company_enrich")
    cutoff = _day(row.get("as_of"))
    starts = {}
    eligible = []
    for profile in _list(_dict(company.get("people")).get("cxos")):
        profile = _dict(profile)
        pid = profile.get("crustdata_person_id")
        details = _dict(_dict(profile.get("experience")).get("employment_details"))
        refresh = _day(profile.get("updated_at") or _dict(profile.get("basic_profile")).get("last_updated"))
        appointments = []
        for role in _list(details.get("current")):
            role = _dict(role)
            ids = role.get("employer_company_id")
            ids = {str(i) for i in (ids if isinstance(ids, list) else [ids]) if i is not None}
            if role.get("crustdata_company_id") is not None:
                ids.add(str(role["crustdata_company_id"]))
            hosts = {_domain(h) for h in _list(role.get("employer_website"))}
            matches = ids == {str(cid)} if ids else bool(hosts.intersection(domains))
            start, _ = _role_date(role.get("employee_start_date") or role.get("start_date"))
            end, valid = _role_date(role.get("employee_end_date") or role.get("end_date"))
            if not matches or not cutoff or not start or start.last > cutoff or not valid or end and end.first <= cutoff:
                continue
            if type(pid) is int and pid > 0:
                starts.setdefault(pid, set()).add(start)
            title = role.get("employee_title") or role.get("title")
            if (ids and refresh and start.first == start.last and start.last <= refresh <= cutoff
                    and isinstance(title, str) and any(INTERIM_CFO.fullmatch(part.strip())
                                                       for part in re.split(r"[,;/&|]|\band\b", title, flags=re.I))):
                # Pass only the fields the prospective review rule consumes.
                appointments.append({"crustdata_company_id": cid, "start_date": str(start.first), "title": title})
        if appointments:
            eligible.append({"basic_profile": {"last_updated": str(refresh)},
                             "experience": {"employment_details": {"current": appointments}}})
    dated = [next(iter(s)) for s in starts.values() if len(s) == 1]
    if len(dated) >= MIN_GROUP:
        detail = (f"{len(dated)} distinct profiles in the executive roster have dated roles at this company. "
                  f"Those reported starts range from {min(s.first for s in dated)} to {max(s.last for s in dated)}.")
        review.card(row, "Executive role starts", detail)
    # Forecast deadlines run forward from the actual review, even when the
    # input contains an earlier observation or a reconstruction of a past role.
    forecast = forecast_window(cid, {"people": {"cxos": eligible}}, review.evidence, datetime.now(timezone.utc).date())
    if forecast:
        day = _day(forecast["observed_on"])
        review.card(row, "Interim finance appointment", f"The indexed interim finance role started on {day}.", observed=day)
    return forecast


def _job_postings(review, cid):
    row = review.one("job_search")
    cutoff = _day(row.get("as_of"))
    dates = []
    for job in _list(_dict(row.get("data")).get("job_listings")):
        job = _dict(job)
        company_id, _ = _identity(_dict(job.get("company")), None)
        posted = _day(_dict(job.get("metadata")).get("date_added"))
        if company_id == cid and posted and cutoff and posted <= cutoff:
            dates.append(posted)
    if dates:
        day = max(dates)
        detail = f"The returned index includes a job posting for this company dated {day}."
        review.card(row, "Indexed job posting", detail, observed=day)


def interpret(desk, subject, inputs, raw):
    """Project a run_live response or its joined lanes into ledger-safe findings.

    Candidate claim accepts the intake text (e.g. "Led 40 engineers, 2023 to
    2025"), or a mapping/JSON object with start_date, end_date, headcount and
    department. The separate claim_start, claim_end, claim_headcount and
    claim_department inputs express the same fields. No free text is retained.
    """
    inputs, raw = _dict(inputs), _dict(raw)
    review = _Review(raw)
    forecast = None
    leadership = None
    if desk in ("payment", "candidate", "company"):
        cid, domains, company_name, company = _company(review, desk, subject, inputs)
    if desk == "company":
        leadership = _named_leadership(review, company, cid, domains, inputs)
        _filings(review, subject, inputs, company_name, domains)
        if company and not leadership:
            _workforce(review, company)
            forecast = _executives(review, company, cid, domains)
        if cid:
            _job_postings(review, cid)
    consent = inputs.get("consent", True) is True and not any(
        _dict(s).get("type") == "consent_required" for s in _list(raw.get("signals")))
    if not consent and (desk == "candidate" or desk == "payment" and inputs.get("person_url")):
        review.step("Profile consent", "skipped", "Profile evidence requires consent.")
    if desk == "payment":
        _payment(review, inputs, cid, domains, consent)
        _vendor_domain(review, inputs, domains)
    elif desk == "candidate":
        _candidate(review, inputs, cid, domains, company_name, company, consent)
    charges = [_credits(_dict(c).get("actual")) for c in _list(raw.get("credits"))]
    result = dict(mode="live", evidence=review.evidence, signals=review.signals, steps=review.steps, flows=[],
                  credits=float(sum(charges)) if charges and all(c is not None for c in charges) else None)
    if review.proposition:
        result["proposition"] = review.proposition
    if forecast:
        result["forecast"] = forecast
    if leadership:
        result["leadership_review"] = leadership
    return result
