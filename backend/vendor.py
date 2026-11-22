"""Payment authority checks with independent vendor-domain records."""
from urllib.parse import urlsplit


def domain(value):
    if not value:
        return ""
    try:
        host = urlsplit(value if "://" in value else "//" + value).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.").rstrip(".")


def vendor_records(inputs, company, rows):
    sender = domain(inputs.get("sender_domain"))
    claimed = domain(inputs.get("domain"))
    basic = company.get("basic_info") or {}
    if not sender or not claimed or claimed == sender or claimed != domain(basic.get("primary_domain")):
        return []
    entity = next((e for e in rows if e["operation"] == "brreg" and e["status"] == "ok"), {})
    registry = entity.get("data") or {}
    legal = str(registry.get("navn") or "").strip().casefold().removesuffix(" as")
    matched = str(basic.get("name") or "").strip().casefold().removesuffix(" as")
    if (not legal or legal != matched or registry.get("organisasjonsnummer") != inputs.get("orgnr")
            or domain(registry.get("hjemmeside")) != claimed):
        return []
    matched_row = next(e for e in rows if e["operation"] == "company_identify" and e["status"] == "ok")
    proposition = f"The supplied sending domain {sender} differs from the vendor's recorded domain {claimed}."
    return [{"id":f"vendor-domain-{i}","source":source,"label":"Vendor domain cross-check",
             "mode":"LIVE","as_of":row["as_of"],"url":row["source"],"claim":proposition,
             "detail":f"{source} lists {claimed} for the matched entity. The request uses {sender}."}
            for i,(source,row) in enumerate([("Crustdata",matched_row),("Brønnøysund",entity)],1)]
