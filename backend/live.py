"""Public browser boundary. Raw provider records never leave this module."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit
from .providers import run_live
from .identity import resolve_public_ids
from .observations import describe
from .colleagues import overlap_count
from .findings import interpret
from .estate import estate_evidence
from .destination import screen_destination
from .progress import report


def collect_live(desk, subject, consent=False, inputs=None):
    supplied = inputs if isinstance(inputs, dict) else {}
    safe = {k: str(supplied[k])[:500] for k in
            ('domain', 'sender_domain', 'person_url', 'ifsc', 'orgnr', 'cik', 'claim', 'lei') if k in supplied}
    safe = resolve_public_ids(desk, subject, safe)
    calls = {}
    person = safe.get('person_url', '')
    if person and consent is True and re.fullmatch(r'https://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_%\-]+/?', person):
        calls['person_enrich'] = {'professional_network_profile_urls': [person],
                                  'fields': ['experience']}
    domain = safe.get('domain', '').lower()
    if domain:
        safe['domain'] = domain
    if desk != 'candidate' or domain:
        calls['company_identify'] = {'domains': [domain], 'exact_match': True} if domain else {'names': [str(subject)[:200]]}
    # The identity, person, and public registry desks can collect independently.
    lanes = [{"crustdata": {operation: payload}} for operation, payload in calls.items()]
    lanes.extend({field: safe[field]} for field in ("orgnr", "cik", "ifsc", "lei") if safe.get(field))
    if desk == "payment" and (safe.get("sender_domain") or domain):
        lanes.append({"domain": safe.get("sender_domain") or domain})
    raw = dict(evidence=[], steps=[], credits=[], flows=[], signals=[])
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(copy_context().run, run_live, desk, "", consent, lane)
                   for lane in lanes]
        for future in futures:
            part = future.result()
            for key in raw:
                raw[key].extend(part[key])
    # Enrich only a unique confident identity; tied name matches remain unresolved.
    identified = next((e['data'] for e in raw['evidence'] if e['operation'] == 'company_identify'), None)
    matches = identified[0].get('matches', []) if isinstance(identified, list) and len(identified) == 1 else []
    matches = [m for m in matches if isinstance(m, dict) and isinstance(m.get('confidence_score'), (int, float)) and m['confidence_score'] >= .8]
    overlap_note = None
    if len(matches) == 1:
        company = matches[0].get('company_data', {})
        cid = company.get('crustdata_company_id') or company.get('basic_info', {}).get('crustdata_company_id')
        if isinstance(cid, int):
            extra = run_live(desk, '', consent, {'crustdata': {'company_enrich': {'crustdata_company_ids': [cid], 'fields': ['basic_info', 'headcount', 'people']}}})
            for key in ('evidence', 'steps', 'credits', 'signals'):
                raw[key].extend(extra[key])
            person_rows = next((e["data"] for e in raw["evidence"] if e["operation"] == "person_enrich"), [])
            if desk == "candidate" and consent and isinstance(person_rows, list) and person_rows:
                matched = person_rows[0].get("matches", [])
                target = matched[0].get("person_data", {}) if len(matched) == 1 else person_rows[0].get("person_data", {})
                company_name = (company.get("basic_info") or {}).get("name")
                if target and company_name:
                    payload = {"filters": {"field": "experience.employment_details.company_name",
                                           "type": "in", "value": [company_name]}, "limit": 25,
                               "fields": ["crustdata_person_id", "experience.employment_details"]}
                    peers = run_live(desk, "", consent, {"crustdata": {"person_search": payload}})
                    for key in ("evidence", "steps", "credits", "signals"):
                        raw[key].extend(peers[key])
                    row = peers["evidence"][0]
                    count = overlap_count(target, row.get("data") or {}, cid)
                    detail = (f"{count} distinct colleagues have a dated overlap in this sample."
                              if count is not None and count >= 5 else
                              "Insufficient dated overlap to publish an aggregate.")
                    overlap_note = dict(source="Crustdata", label="Colleague overlap", detail=detail,
                                        as_of=row["as_of"], mode="LIVE", url=row["source"])
    evidence = []
    for e in raw['evidence']:
        detail = describe(e)
        evidence.append(dict(source=e['provider'], label=e['operation'], detail=detail,
                             as_of=e['as_of'], mode='LIVE', url=e['source']))
    if overlap_note:
        evidence.append(overlap_note)
    credits = [c.get('actual') for c in raw['credits']]
    result = dict(evidence=evidence, steps=[dict(name=s['operation'], status=s['status'], detail='Provider collection') for s in raw['steps']],
                  flows=[], credits=sum(float(c) for c in credits) if credits and all(c is not None for c in credits) else None,
                  signals=raw['signals'])
    interpreted = interpret(desk, subject, {**safe, "consent": consent}, raw)
    result["evidence"].extend(interpreted["evidence"])
    result["steps"].extend(step for step in interpreted["steps"] if step not in result["steps"])
    result["signals"].extend(interpreted["signals"])
    result.update(mode="live", subject=subject, consent=consent)
    if person and consent is not True:
        result['signals'].append(dict(type='consent_required', provider='crustdata', operation='person_enrich', status='skipped'))
    if desk == "estate" and len(matches) == 1:
        registry = next((e.get("data") for e in raw["evidence"] if e["operation"] == "brreg"), {}) or {}
        registry_name = str(registry.get("navn") or "").casefold().strip()
        company_name = (company.get("basic_info") or {}).get("name", "").casefold().strip()
        website = str(registry.get("hjemmeside") or "").lower()
        registry_host = (urlsplit(website if "://" in website else "//" + website).hostname or "").removeprefix("www.")
        basic = company.get("basic_info") or {}
        alias_bound = (registry_host and registry_host == basic.get("primary_domain")
                       and registry_name.removesuffix(" as") == company_name.removesuffix(" as"))
        if registry_name and (registry_name == company_name or alias_bound) and registry.get("konkurs") is True:
            filed = registry.get("konkursdato")
            report("Estate employee flows", "running", "Examining dated employment histories in aggregate")
            estate = estate_evidence(subject, domain, company, filed, datetime.now(timezone.utc))
            result["evidence"].extend(estate["evidence"])
            result["flows"] = estate["flows"]
            result["steps"].extend(estate["steps"])
            if estate["steps"] and any(step["name"] == "person_search" for step in estate["steps"]):
                result["credits"] = (round(result["credits"] + estate["credits"], 4)
                                     if result["credits"] is not None and estate["credits"] is not None else None)
            roles = next((e.get("data") for e in raw["evidence"] if e["operation"] == "brreg_roles"), {})
            charges = []
            result["evidence"].extend(screen_destination(estate["flows"], safe.get("orgnr"), roles, filed, charges))
            for charge in charges:
                result["credits"] = (round(result["credits"] + float(charge), 4)
                                     if result["credits"] is not None and charge is not None else None)
            if (estate.get("unknown") or 0) >= 5:
                result["flows"] = [*result["flows"], {"from": company_name, "to": "Unknown or suppressed",
                                                      "count": estate["unknown"]}]
            report("Estate employee flows", estate["status"], "Estate cohort review complete")
    return result
