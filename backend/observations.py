"""Display-safe observations shared by all four desks."""


def describe(row):
    data = row.get("data")
    op = row["operation"]
    if row["status"] != "ok":
        return f"Collection returned {row['status']}. This source contributes no finding."
    if op in ("company_identify", "company_enrich"):
        matches = data[0].get("matches", []) if isinstance(data, list) and len(data) == 1 else []
        if not matches:
            return "No company matched this identifier."
        first = matches[0]
        company = first.get("company_data", {})
        basic = company.get("basic_info", {})
        if op == "company_identify":
            confidence = first.get("confidence_score")
            score = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "unknown"
            return (f"{len(matches)} candidate match(es). Leading record: {basic.get('name', 'unknown')}, "
                    f"{basic.get('primary_domain') or 'domain unknown'}. Match confidence {score}.")
        headcount = company.get("headcount") or {}
        size = headcount.get("total")
        if isinstance(size, int) and size >= 5:
            return f"{basic.get('name') or 'Matched company'} has {size} profiles in the provider headcount estimate."
        return "Matched company profile retrieved. Workforce count unavailable or suppressed."
    if not isinstance(data, dict):
        return "Record retrieved. Review the source for context."
    if op == "brreg":
        name = data.get("navn", "Unknown entity")
        status = "Bankruptcy registered" if data.get("konkurs") else "No current bankruptcy flag"
        date = data.get("konkursdato")
        count = data.get("antallAnsatte")
        size = f" Registered employees: {count}." if isinstance(count, int) and count >= 5 else ""
        return f"{name} ({data.get('organisasjonsnummer')}). {status}{' on ' + date if date else ''}.{size}"
    if op == "brreg_roles":
        return "Statutory roles record retrieved. Personal identifiers are excluded from the ledger."
    if op == "rdap":
        dates = [e["eventDate"][:10] for e in data.get("events", [])
                 if e.get("eventAction") == "registration" and isinstance(e.get("eventDate"), str)]
        return "Domain registered on " + dates[0] + "." if dates else "Registry returned no registration date."
    if op == "ifsc":
        return ", ".join(str(data[k]) for k in ("BANK", "BRANCH", "CITY", "IFSC") if data.get(k))
    if op == "submissions":
        return f"Filing index retrieved for {data.get('name', 'issuer')}, CIK {data.get('cik', 'unknown')}."
    if op == "job_search":
        listings = data.get("job_listings") or []
        latest = (listings[0].get("metadata") or {}).get("date_added") if listings else None
        count = data.get("total_count")
        return ((f"{count} indexed postings. " if isinstance(count, int) else "")
                + (f"Most recent posting date: {latest[:10]}." if isinstance(latest, str) else "Latest posting date unavailable."))
    if op == "gleif":
        entity = data.get("data", {}).get("attributes", {}).get("entity", {})
        return f"Registered legal name: {entity.get('legalName', {}).get('name', 'unavailable')}."
    return "Record retrieved. Relevant dated observations require independent review."
