"""Public browser boundary. Raw provider records never leave this module."""
import os
import re
from .providers import run_live


def collect_live(desk, subject, consent=False, inputs=None):
    supplied = inputs if isinstance(inputs, dict) else {}
    safe = {k: str(supplied[k])[:500] for k in
            ('domain', 'person_url', 'ifsc', 'orgnr', 'cik', 'claim') if k in supplied}
    calls = {}
    person = safe.get('person_url', '')
    if person and consent is True and re.fullmatch(r'https://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_%\-]+/?', person):
        calls['person_enrich'] = {'professional_network_profile_urls': [person],
                                  'fields': ['experience']}
    domain = safe.get('domain', '').lower()
    if domain:
        safe['domain'] = domain
    calls['company_identify'] = {'domains': [domain], 'exact_match': True} if domain else {'names': [str(subject)[:200]]}
    raw = run_live(desk, subject, consent, {**safe, 'crustdata': calls})
    # Enrich only a unique confident identity; tied name matches remain unresolved.
    identified = next((e['data'] for e in raw['evidence'] if e['operation'] == 'company_identify'), None)
    matches = identified[0].get('matches', []) if isinstance(identified, list) and len(identified) == 1 else []
    matches = [m for m in matches if isinstance(m, dict) and isinstance(m.get('confidence_score'), (int, float)) and m['confidence_score'] >= .95]
    if len(matches) == 1:
        company = matches[0].get('company_data', {})
        cid = company.get('crustdata_company_id') or company.get('basic_info', {}).get('crustdata_company_id')
        if isinstance(cid, int):
            extra = run_live(desk, '', consent, {'crustdata': {'company_enrich': {'crustdata_company_ids': [cid], 'fields': ['basic_info', 'headcount', 'people']}}})
            for key in ('evidence', 'steps', 'credits', 'signals'):
                raw[key].extend(extra[key])
    evidence = []
    for e in raw['evidence']:
        detail = 'Source unavailable; no inference.'
        data = e.get('data')
        if e['status'] == 'ok':
            detail = 'Record retrieved; identity and independent corroboration required.'
            if e['provider'] == 'ifsc' and isinstance(data, dict):
                detail = '; '.join(f'{k}: {data[k]}' for k in ('BANK', 'BRANCH', 'IFSC') if isinstance(data.get(k), str))
            if e['provider'] == 'brreg' and isinstance(data, dict):
                detail = '; '.join(f'{k}: {data[k]}' for k in ('organisasjonsnummer', 'navn', 'registreringsdatoEnhetsregisteret', 'stiftelsesdato', 'konkurs') if isinstance(data.get(k), (str, bool)))
            if e['provider'] == 'sec' and isinstance(data, dict):
                detail = '; '.join(f'{k}: {data[k]}' for k in ('cik', 'name', 'sicDescription') if isinstance(data.get(k), (str, int)))
        evidence.append(dict(source=e['provider'], label=e['operation'], detail=detail,
                             as_of=e['as_of'], mode='LIVE', url=e['source']))
    credits = [c.get('actual') for c in raw['credits']]
    result = dict(evidence=evidence, steps=[dict(name=s['operation'], status=s['status'], detail='Provider collection') for s in raw['steps']],
                  flows=[], credits=sum(float(c) for c in credits) if credits and all(c is not None for c in credits) else None,
                  signals=raw['signals'])
    if person and consent is not True:
        result['signals'].append(dict(type='consent_required', provider='crustdata', operation='person_enrich', status='skipped'))
    return result
