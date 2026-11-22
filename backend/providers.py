"""Synchronous live evidence collection; no routing or verdicts."""
from .progress import report

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_lock = threading.Lock()
_next = {}


def throttle(key, interval):
    with _lock:
        now = time.monotonic()
        wait = max(0, _next.get(key, now) - now)
        _next[key] = now + wait + interval
    time.sleep(wait)


OPERATIONS = {name: '/' + name.replace('_', '/') for name in (
    'company_identify', 'person_identify', 'company_enrich', 'person_enrich',
    'company_search', 'person_search', 'job_search', 'batch_person_verify',
    'watch_company', 'watch_person', 'account_endpoints', 'account_credits')}


def run_live(desk, subject, consent=False, inputs=None):
    inputs = inputs or {}
    result = dict(evidence=[], steps=[], credits=[], flows=[], signals=[])

    def call(provider, operation, url, payload=None, headers=None, unavailable=False):
        owner = 'identity' if operation.endswith('_identify') else 'material' if provider == 'crustdata' else 'sources'
        report(operation, 'running', f'Collecting {provider} evidence', collection_agent=owner)
        eid = 'e' + str(len(result['evidence']) + 1)
        status, data, used = 'unavailable', None, None
        if not unavailable:
            throttle(provider + operation, 12 if provider == 'crustdata' else 1)
            if provider == 'crustdata':
                throttle('crustdata:overall', .6)
            try:
                req = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                              headers={'Accept': 'application/json', 'Content-Type': 'application/json', **(headers or {})})
                try:
                    response = build_opener(NoRedirect()).open(req, timeout=20)
                except HTTPError as exc:
                    response = exc
                with response:
                    raw_used = response.headers.get('X-Credits-Used')
                    try:
                        value = Decimal(raw_used) if raw_used else None
                        used = str(value) if value is not None and value.is_finite() and value >= 0 else None
                    except InvalidOperation:
                        pass
                    code = response.code
                    status = 'ok' if 200 <= code < 300 else ('rate_limited' if code == 429 else 'http_' + str(code))
                    if status == 'ok':
                        raw = response.read(4_000_001)
                        if len(raw) > 4_000_000:
                            status = 'response_too_large'
                        else:
                            data = json.loads(raw)
            except (URLError, TimeoutError, OSError, ValueError):
                status = 'transport_or_decode_failure'
        result['evidence'].append(dict(id=eid, provider=provider, operation=operation,
            as_of=datetime.now(timezone.utc).isoformat(), status=status, data=data, source=url.split('?')[0]))
        result['steps'].append(dict(provider=provider, operation=operation, status=status))
        if provider == 'crustdata':
            result['credits'].append(dict(evidence_id=eid, actual=used))
        kind = 'evidence_available' if status == 'ok' else ('provider_unavailable' if status == 'unavailable' else 'provider_failure')
        result['signals'].append(dict(type=kind, provider=provider, operation=operation, evidence_id=eid, status=status))
        report(operation, status, f'{provider} collection finished', collection_agent=owner)
        return data

    key = os.getenv('CRUSTDATA_API_KEY')
    headers = {'Authorization': 'Bearer ' + (key or ''), 'x-api-version': '2025-11-01'}
    calls = dict(inputs.get('crustdata', {}))
    # Account diagnostics are explicit internal calls only.
    if not inputs.get('crustdata') and subject:
        calls['company_identify'] = {'names': [str(subject)]}
    for operation, payload in calls.items():
        if operation not in OPERATIONS:
            continue
        if (operation.startswith('person') or operation == 'batch_person_verify') and consent is not True:
            result['signals'].append(dict(type='consent_required', provider='crustdata', operation=operation, status='skipped'))
            continue
        if operation.startswith('watch_'):
            # Explicit entity list only. Never infer a watch from a search or subject.
            if not (inputs.get('watch_confirmed') is True and inputs.get('watch_scope') == subject
                    and isinstance(payload, dict) and payload.get('sla_days') == 30
                    and payload.get('scope') == subject
                    and payload.get('entities') == inputs.get('watch_entities')
                    and isinstance(payload.get('entities'), dict)
                    and sum(len(v) for v in payload['entities'].values() if isinstance(v, list)) == 1
                    and payload.get('config', {}).get('refresh_frequency_days', 30) == 30):
                result['steps'].append(dict(provider='crustdata', operation=operation, status='scope_required'))
                continue
            payload = {k: v for k, v in payload.items() if k not in ('scope', 'sla_days')}
        call('crustdata', operation, 'https://api.crustdata.com' + OPERATIONS[operation],
             None if operation.startswith('account_') else payload, headers, not key)

    def witness(name, url):
        return call(name, name, url)

    org = str(inputs.get('orgnr', ''))
    if re.fullmatch(r'\d{9}', org):
        witness('brreg', 'https://data.brreg.no/enhetsregisteret/api/enheter/' + org)
        witness('brreg_roles', 'https://data.brreg.no/enhetsregisteret/api/enheter/' + org + '/roller')
    cik = str(inputs.get('cik', ''))
    if re.fullmatch(r'\d{1,10}', cik):
        ua = os.getenv('SEC_USER_AGENT')
        call('sec', 'submissions', 'https://data.sec.gov/submissions/CIK' + cik.zfill(10) + '.json',
             headers={'User-Agent': ua or ''}, unavailable=not ua)
    domain = str(inputs.get('domain', '')).lower()
    if desk == 'payment' and re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        # Registry endpoints from IANA's DNS RDAP bootstrap. Keep requests on fixed origins.
        registries = {
            'com': 'https://rdap.verisign.com/com/v1/',
            'net': 'https://rdap.verisign.com/net/v1/',
            'org': 'https://rdap.publicinterestregistry.org/rdap/',
            'no': 'https://rdap.norid.no/',
            'ai': 'https://rdap.identitydigital.services/rdap/',
        }
        registry = registries.get(domain.rsplit('.', 1)[-1])
        if registry:
            witness('rdap', registry + 'domain/' + domain)
        if inputs.get('domain_history'):
            witness('crtsh', 'https://crt.sh/?' + urlencode({'q': domain, 'output': 'json'}))
            witness('wayback', 'https://web.archive.org/cdx/search/cdx?' + urlencode({'url': domain + '/', 'output': 'json', 'filter': 'statuscode:200', 'limit': 20}))
    if inputs.get('ifsc') and re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', str(inputs['ifsc'])):
        witness('ifsc', 'https://ifsc.razorpay.com/' + inputs['ifsc'])
    if inputs.get('iban') and re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{10,30}', str(inputs['iban'])):
        witness('openiban', 'https://openiban.com/validate/' + quote(inputs['iban']) + '?getBIC=true&validateBankCode=true')
    if inputs.get('lei') and re.fullmatch(r'[A-Z0-9]{20}', str(inputs['lei'])):
        witness('gleif', 'https://api.gleif.org/api/v1/lei-records/' + inputs['lei'])
    return result
