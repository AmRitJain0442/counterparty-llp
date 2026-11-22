"""Screen the largest publishable workforce destination for ordinary explanations."""
import re
from datetime import date

from .identity import resolve_public_ids
from .providers import run_live


def _directors(data):
    people = set()
    for group in (data or {}).get("rollegrupper", []):
        if (group.get("type") or {}).get("kode") != "STYR":
            continue
        for role in group.get("roller", []):
            if role.get("fratraadt"):
                continue
            person = role.get("person") or {}
            name = person.get("navn") or {}
            dob = person.get("fodselsdato")
            full = " ".join(str(name.get(k) or "").strip().casefold()
                            for k in ("fornavn", "mellomnavn", "etternavn")).strip()
            if dob and full:
                people.add((full, dob))
    return people


def screen_destination(flows, origin, role_record, failed_on, charges):
    eligible = [f for f in flows if f.get("count", 0) >= 5 and f.get("to")
                and f["to"].lower() not in ("unknown", "other", "unresolved")]
    if not eligible or not failed_on:
        return []
    destination = max(eligible, key=lambda f: f["count"])["to"]
    alias = destination
    if "." in alias or alias.startswith("Crustdata company "):
        if re.fullmatch(r"Crustdata company [1-9][0-9]*", alias):
            payload = {"crustdata_company_ids": [int(alias.split()[-1])]}
        else:
            payload = {"domains": [alias], "exact_match": True}
        found = run_live("estate", "", False, {"crustdata": {"company_identify": payload}})
        charges.extend(item.get("actual") for item in found["credits"])
        rows = found["evidence"][0].get("data") or []
        matches = rows[0].get("matches", []) if rows else []
        exact = [m for m in matches if m.get("confidence_score", 0) >= .8]
        if len(exact) != 1:
            return []
        destination = exact[0]["company_data"]["basic_info"]["name"]
    org = resolve_public_ids("estate", destination, {}).get("orgnr")
    if not org or org == origin:
        return []
    rows = run_live("estate", "", False, {"orgnr": org})["evidence"]
    entity = next((e for e in rows if e["provider"] == "brreg" and e["status"] == "ok"), None)
    if not entity:
        return []
    founded = entity["data"].get("stiftelsesdato")
    notes = []
    if founded:
        try:
            if date.fromisoformat(founded) < date.fromisoformat(failed_on):
                notes.append(f"The destination was already incorporated on {founded}. "
                             "This rules out formation of this entity after the bankruptcy.")
        except ValueError:
            pass
    roles = next((e["data"] for e in rows if e["provider"] == "brreg_roles" and e["status"] == "ok"), None)
    if _directors(role_record) & _directors(roles):
        notes.append("The two statutory boards share a director. A shared appointment alone does not establish succession.")
    if not notes:
        return []
    return [{"source": "Brønnøysund", "label": f"Opposing counsel · {destination}",
             "detail": " ".join(notes), "as_of": entity["as_of"], "mode": "LIVE", "url": entity["source"]}]
