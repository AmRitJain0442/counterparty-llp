"""Analytical personas for the council and a local evidence check per specialist.

Persona and task strings are prompt material for the live Gemini path. Nothing here
calls a model: ``demo_specialist`` is a deterministic rehearsal that inspects only
the display-safe evidence rows it is given and cites only ids found in those rows.
"""
import re
from datetime import date

PARENT_PERSONAS = {
    'identity': (
        'Identity resolver: a former KYC onboarding reviewer who treats a name as a hypothesis, never a '
        'finding. Insists that every later conclusion rest on an explicit, attributable binding between the '
        'subject and the records, and says plainly when that binding is only probable.'),
    'sources': (
        'Source auditor: a records-management lawyer who reads provenance before content. Asks who produced '
        'each exhibit, whether it can be retrieved again, and whether two exhibits are truly independent or '
        'one echoing the other.'),
    'dates': (
        'Date auditor: a forensic accountant who reconstructs timelines from stamps rather than narrative. '
        'Separates when something happened from when it was observed, and distrusts any ordering the '
        'dates do not support.'),
    'analyst_scope': (
        'Scope analyst: an evidence-minded corporate investigator who tests whether a claim and its '
        'support describe the same entity, unit, population and quantity. Reports the narrowest statement '
        'the exhibits can bear.'),
    'analyst_timing': (
        'Timing analyst: a sequence-of-events reviewer who builds the chronology from dated observations '
        'and tests whether the claimed order, lag and period actually follow. Flags what cannot be placed in time.'),
    'material': (
        'Material evidence clerk: a disciplined case-file indexer who decides what is relevant, '
        'substantive and of what quality. Selects exhibits for the decision and leaves out filler without hiding it.'),
    'challenger_scope': (
        'Scope challenger: opposing counsel who argues the most credible innocent or narrower reading of '
        'the exhibits. Names a specific source, the alternative it permits and the check that would '
        'distinguish it.'),
    'challenger_timing': (
        'Timing challenger: a sceptical reviewer of chronology and sample size who asks whether coincidence, '
        'reporting lag or a thin cohort would produce the same exhibits. Requires a distinguishing test.'),
    'gaps': (
        'Evidence gaps clerk: a quality-assurance auditor who inventories what is missing, unavailable or '
        'uncorroborated. Treats absence of evidence as an open item, never as support.'),
    'partner': (
        'Review partner: a senior reviewer who reconciles the analysts and the challengers. States where '
        'they agree, where they do not, and the single most useful next action for a human.'),
    'authority': (
        'Verdict custodian: a controls officer who preserves the deterministic adjudication. Verifies that '
        'the proposed finding is traceable to cited exhibits and never revises or second-guesses it.'),
    'handoff': (
        'Handoff clerk: a case-file archivist who closes the loop. Indexes what was filed, flags exhibits '
        'nobody cited and lists open items so a reviewer can pick up without rereading everything.'),
}


def _spec(sid, name, persona, task):
    return dict(id=sid, name=name, persona=persona, task=task)


SPECIALISTS = {
    'identity': (
        _spec('identity.registry_match', 'Registry binding checker',
              'A corporate-registry examiner who trusts only identifiers issued by a registrar, regulator or '
              'standards body, and checks that an exhibit carries one before treating it as bound to the subject.',
              'Check whether any exhibit binds the subject to a registrar-issued record or identifier.'),
        _spec('identity.alias_collision', 'Alias collision checker',
              'A name-matching specialist who assumes lookalikes exist. Counts candidates and reads match '
              'confidence before accepting that a leading record is the subject.',
              'Check for competing candidates, low match confidence or conflicting names among the exhibits.'),
    ),
    'sources': (
        _spec('sources.provenance', 'Provenance checker',
              'A chain-of-custody reviewer who requires each exhibit to name its source and say whether it was '
              'retrieved live, rehearsed or synthesised.',
              'Check that every exhibit names an attributable source and state its retrieval mode.'),
        _spec('sources.independence', 'Independence checker',
              'A circular-reporting hunter who traces exhibits back to their root and refuses to count one '
              'root twice or count a replay as a second witness.',
              'Count independent source roots and exclude replays and duplicated roots.'),
    ),
    'dates': (
        _spec('dates.recency', 'Recency checker',
              'A freshness auditor who compares observation dates with each other and flags undated or '
              'stale exhibits that could describe a previous state of affairs.',
              'Check which exhibits carry an observation date and how far apart they are.'),
        _spec('dates.sequence', 'Date plausibility checker',
              'A timeline sceptic who looks for dates inside exhibit text that are later than the exhibit '
              'was observed, or that are malformed.',
              'Check dates cited inside exhibit text for impossible or future-dated values.'),
    ),
    'analyst_scope': (
        _spec('scope.quantity_reconciliation', 'Quantity reconciler',
              'A reconciliation analyst who lines up every figure attached to the claim and does not '
              'assume that two numbers refer to the same population.',
              'Reconcile the figures stated in claim-bearing exhibits and report any divergence.'),
        _spec('scope.entity_boundary', 'Entity boundary checker',
              'A group-structure analyst who asks whether an exhibit speaks for the entity, its parent, '
              'its unit or a cohort, and whether the claim uses the same boundary.',
              'Check which entity, unit or cohort boundary each claim-bearing exhibit actually states.'),
    ),
    'analyst_timing': (
        _spec('timing.event_order', 'Event order checker',
              'A chronology analyst who sorts every dated event and tests relative-order language such as '
              '"before" or "predates" against the dates themselves.',
              'Build the chronology from dated events and test any stated ordering.'),
        _spec('timing.lag_window', 'Lag and period checker',
              'A reporting-lag analyst who compares event dates with retrieval dates and checks that '
              'periods named in different exhibits actually line up.',
              'Measure lag between events and observation, and check period alignment.'),
    ),
    'material': (
        _spec('material.relevance', 'Relevance selector',
              'A case-file selector who keeps exhibits with a concrete, dated, specific observation and '
              'sets aside generic boilerplate.',
              'Separate substantive exhibits from generic or empty ones.'),
        _spec('material.source_tier', 'Evidence tier grader',
              'An evidence-weight assessor who grades exhibits as primary record, provider reconstruction, '
              'self-asserted or rehearsal, and will not let a lower tier stand in for a higher one.',
              'Grade the exhibits by evidence tier and report the best tier present.'),
    ),
    'challenger_scope': (
        _spec('challenge.alt_explanation', 'Alternative explanation drafter',
              'A defence-side analyst who builds the most plausible benign explanation from a specific '
              'exhibit and proposes the one check that would rule it in or out.',
              'Name one plausible alternative explanation anchored to a specific exhibit and a way to test it.'),
        _spec('challenge.contrary_evidence', 'Contrary evidence scout',
              'A devil\'s advocate who searches the exhibits for anything that cuts against the claim, '
              'and who reports honestly when nothing does.',
              'Find exhibits that contradict, narrow or fail to support the claim.'),
    ),
    'challenger_timing': (
        _spec('challenge.timing_alternative', 'Timing alternative drafter',
              'A coincidence sceptic who asks whether observation dates are really event dates and whether '
              'the sequence could be an artefact of when the data were collected.',
              'Check whether stated dates are event dates or merely retrieval dates.'),
        _spec('challenge.sample_size', 'Sample size checker',
              'A statistical reviewer who looks for small counts, suppressed cells and unstated denominators '
              'before accepting a cohort-based statement.',
              'Check the counts quoted in the exhibits for thin or suppressed samples.'),
    ),
    'gaps': (
        _spec('gaps.unavailable_sources', 'Unavailable source auditor',
              'A completeness auditor who lists every source that failed, was suppressed or returned '
              'nothing, and says what each failure prevents.',
              'List exhibits that were unavailable, empty or suppressed.'),
        _spec('gaps.missing_corroboration', 'Corroboration gap auditor',
              'A corroboration auditor who works claim by claim and lists the source classes still '
              'absent for each.',
              'List claims backed by a single source class and the source classes not present.'),
    ),
    'partner': (
        _spec('partner.agreement_map', 'Agreement mapper',
              'A review-meeting chair who maps which challengers raised concerns, which closed them and '
              'where the council remains split.',
              'Map agreement and disagreement across the completed upstream reports.'),
        _spec('partner.reviewer_questions', 'Reviewer question drafter',
              'A senior associate who turns open concerns into specific questions a human reviewer can '
              'answer in minutes, each tied to an exhibit.',
              'Draft concrete reviewer questions tied to specific exhibits.'),
    ),
    'authority': (
        _spec('authority.verdict_integrity', 'Verdict integrity checker',
              'A controls tester who confirms that the proposed verdict is present, unmodified and '
              'supported by at least one material exhibit, without ever recomputing it.',
              'Confirm the proposed verdict is preserved verbatim and has material support.'),
        _spec('authority.evidence_trace', 'Evidence trace checker',
              'An audit-trail reviewer who traces the verdict to the exhibits that carry a claim and '
              'flags any that are rehearsal or undated.',
              'Trace the verdict to claim-bearing exhibits and flag rehearsal or undated ones.'),
    ),
    'handoff': (
        _spec('handoff.receipt_index', 'Receipt indexer',
              'A records clerk who indexes each upstream report with its status and citations and notes '
              'exhibits that no report cites.',
              'Index upstream reports and list exhibits that no report cites.'),
        _spec('handoff.open_items', 'Open item collector',
              'A hand-over coordinator who collects unresolved items and states plainly what a rehearsal '
              'does and does not establish.',
              'Collect open items for the reviewer and disclose the evidence mode.'),
    ),
}

_ISO = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
_IDENT = re.compile(r'\b\d{6,}\b|\b[A-Z]{4}0[A-Z0-9]{6}\b|\b[A-Z0-9]{20}\b|\b(?:CIK|LEI|orgnr)\W+\w+', re.I)
_QUARTER = re.compile(r'\bQ([1-4])\s*(20\d{2})\b')
_BAD = re.compile(r'\b(no |not |fails?|failed|differs?|unavailable|suppressed|revoked|killed|predat\w+|'
                  r'unresolved|without|contradict\w*)', re.I)
_GENERIC = re.compile(r'(review the source|retrieved\.?$|no company matched|returned \w+\. this source contributes no)', re.I)
_REGISTRY = re.compile(r'\b(registry|register|brreg|br[øo]nn[øo]ysund|gleif|edgar|sec|companies house|'
                       r'ifsc|rdap|attestation|filing)\b', re.I)
_SELF = re.compile(r'\b(cv|consented|claims?)\b', re.I)
_BOUNDARY = ('parent', 'subsidiary', 'unit', 'division', 'group', 'branch', 'cohort', 'holding',
             'legal entity', 'reporting unit', 'successor', 'board')
_ALTERNATIVES = (
    (r'headcount|profiles|cohort|estimate|engineer', 'a provider coverage or sampling artefact in the reconstructed workforce count',
     'compare the figure with a dated employer return or payroll extract'),
    (r'filing|registry|incorporated|officer|board', 'a record that belongs to a related entity rather than the subject',
     'confirm the registrar identifier and legal name on the filing itself'),
    (r'domain|registered', 'a benign recent registration such as a rebrand or a new mailbox provider',
     'ask the counterparty to confirm the domain through a known contact'),
    (r'branch|bank|ifsc', 'a legitimate branch migration or merger of the receiving bank',
     'verify the branch change against the bank\'s own notice'),
    (r'appointment|transition|employer|employee|revoc|mandate', 'an internal re-titling or an acting appointment rather than a departure',
     'check the next dated filing or the supplier register entry'),
)


def _rid(row):
    return str(row.get('id') or '')


def _text(row):
    return f"{row.get('label', '')} {row.get('detail', '')}"


def _ids(rows):
    return list(dict.fromkeys(_rid(r) for r in rows if _rid(r)))


def _material(rows):
    return [r for r in rows if r.get('id') and r.get('status', 'ok') in ('ok', 'complete')
            and (r.get('detail') or r.get('label'))]


def _claim_rows(rows):
    return [r for r in _material(rows) if r.get('claim')]


def _isodates(text):
    out = []
    for y, m, d in _ISO.findall(str(text)):
        try:
            out.append(date(int(y), int(m), int(d)))
        except ValueError:
            out.append(None)
    return out


def _asof(row):
    parsed = _isodates(str(row.get('as_of') or '')[:10])
    return parsed[0] if parsed else None


def _is_rehearsal(row):
    return str(row.get('mode', '')).upper() in ('DEMO', 'REPLAY') or 'replay' in str(row.get('source', '')).lower()


def _root(row):
    url = str(row.get('url') or '')
    host = re.sub(r'^\w+://', '', url).split('/')[0].lower()
    return host or str(row.get('source') or 'unknown').lower()


def _tier(row):
    text = f"{row.get('source', '')} {_text(row)}"
    if _is_rehearsal(row) and 'replay' in str(row.get('source', '')).lower():
        return 'rehearsal'
    if _SELF.search(str(row.get('source', ''))):
        return 'self-asserted'
    if _REGISTRY.search(text) and 'crustdata' not in str(row.get('source', '')).lower():
        return 'primary record'
    return 'provider reconstruction'


def _short(items, limit=3):
    items = [str(i) for i in items]
    return ', '.join(items[:limit]) + (f' (+{len(items) - limit})' if len(items) > limit else '')


def _caveat(upstream):
    bad = [u.get('name') or u.get('agent_id') for u in upstream
           if u.get('status') != 'complete' or u.get('assessment') == 'needs_evidence']
    return f' Upstream open: {_short(bad)}.' if bad else ''


def _result(note, assessment, refs, rows, upstream, *, gate=False):
    known = {_rid(r) for r in rows}
    refs = [r for r in dict.fromkeys(refs) if r in known]
    if gate and any(u.get('status') != 'complete' for u in upstream):
        assessment = 'needs_evidence'
    if not refs:
        assessment = 'needs_evidence'
    return dict(note=note[:700], assessment=assessment, refs=refs)


def _identity_registry_match(rows, up, verdict):
    mat = _material(rows)
    bound = [r for r in mat if _tier(r) == 'primary record'
             and _IDENT.search(_ISO.sub(' ', _text(r)))]
    if bound:
        return (f'{len(bound)} registrar-sourced exhibit(s) carry an identifier: {_short(_ids(bound))}. '
                'Gap: the identifier is not shown to be the subject without a human match to the intake.', 'ready', _ids(bound))
    named = [r for r in mat if _tier(r) == 'primary record']
    if named:
        return (f'Registry-type exhibit(s) {_short(_ids(named))} state no identifier. '
                'Gap: binding rests on the name alone.', 'needs_evidence', _ids(named))
    return ('No registrar-sourced exhibit supplied. Gap: the subject is bound to the records only by '
            'provider matching.', 'needs_evidence', _ids(mat[:2]))


def _identity_alias_collision(rows, up, verdict):
    mat = _material(rows)
    hits, concern = [], []
    for r in mat:
        m = re.search(r'(\d+) candidate match', _text(r))
        c = re.search(r'confidence (\d+)%', _text(r))
        if m or c:
            hits.append(r)
            if (m and int(m.group(1)) > 1) or (c and int(c.group(1)) < 80):
                concern.append(r)
    if concern:
        return (f'Ambiguous identity match in {_short(_ids(concern))}: multiple candidates or confidence below 80%. '
                'Gap: leading record is not confirmed as the subject.', 'needs_evidence', _ids(concern))
    if hits:
        return (f'Match exhibit(s) {_short(_ids(hits))} show a single candidate at 80% or higher. '
                'Gap: no independent check for a same-name entity.', 'ready', _ids(hits))
    return ('No exhibit reports candidate counts or match confidence, so lookalike risk was not measured.',
            'needs_evidence', _ids(mat[:1]))


def _sources_provenance(rows, up, verdict):
    mat = _material(rows)
    anon = [r for r in mat if not str(r.get('source') or '').strip()]
    modes = {}
    for r in mat:
        modes.setdefault(str(r.get('mode') or 'unlabelled').upper(), []).append(r)
    mode_text = ', '.join(f'{k} {len(v)}' for k, v in modes.items()) or 'none'
    sources = sorted({str(r.get('source')) for r in mat if r.get('source')})
    if anon:
        return (f'{len(anon)} exhibit(s) name no source: {_short(_ids(anon))}. Modes: {mode_text}.',
                'needs_evidence', _ids(anon))
    return (f'All {len(mat)} material exhibit(s) name a source ({_short(sources, 4)}). Modes: {mode_text}. '
            'Gap: naming a source does not prove independent retrieval.', 'ready' if mat else 'needs_evidence', _ids(mat))


def _sources_independence(rows, up, verdict):
    mat = _claim_rows(rows) or _material(rows)
    live = [r for r in mat if not (_is_rehearsal(r) and 'replay' in str(r.get('source', '')).lower())]
    roots = {}
    for r in live:
        roots.setdefault(_root(r), []).append(r)
    excluded = len(mat) - len(live)
    note = f'{len(roots)} independent root(s) across {len(live)} exhibit(s)'
    if excluded:
        note += f'; {excluded} replay exhibit(s) not counted'
    dup = [k for k, v in roots.items() if len(v) > 1]
    if dup:
        note += f'; shared root: {_short(dup)}'
    ok = len(roots) >= 2
    note += '.' if ok else '. Gap: a single root cannot corroborate itself.'
    return note, 'ready' if ok else 'needs_evidence', _ids(mat)


def _dates_recency(rows, up, verdict):
    mat = _material(rows)
    dated = [(r, _asof(r)) for r in mat if _asof(r)]
    undated = [r for r in mat if not _asof(r)]
    if not dated:
        return ('No material exhibit carries an observation date. Gap: freshness cannot be assessed.',
                'needs_evidence', _ids(mat[:2]))
    days = sorted(d for _, d in dated)
    span = (days[-1] - days[0]).days
    note = f'{len(dated)} of {len(mat)} exhibit(s) dated, {days[0]} to {days[-1]} ({span} day span).'
    if undated:
        note += f' Undated: {_short(_ids(undated))}.'
    return note, ('needs_evidence' if undated else 'ready'), _ids([r for r, _ in dated] + undated)


def _dates_sequence(rows, up, verdict):
    bad, checked = [], []
    for r in _material(rows):
        seen = _asof(r)
        for d in _isodates(r.get('detail', '')):
            checked.append(r)
            if d is None or (seen and d > seen):
                bad.append(r)
    if bad:
        return (f'Impossible or future-dated text in {_short(_ids(bad))}: cited date is malformed or later than '
                'the observation date.', 'needs_evidence', _ids(bad))
    if checked:
        return (f'{len(checked)} date(s) cited inside exhibit text in {_short(_ids(checked))}; none is later than '
                'its observation date.', 'ready', _ids(checked))
    return ('No exhibit text cites an explicit date. Gap: stated timings such as "days before" cannot be '
            'checked against a calendar.', 'needs_evidence', _ids(_material(rows)[:2]))


_WORDS = {w: i for i, w in enumerate(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen '
    'sixteen seventeen eighteen nineteen twenty'.split())}
_UNIT = r'(?:distinct |reconstructed )?(?:profiles|engineers|employees|staff|people|postings|observations)'
_COUNT = re.compile(rf'\b(\d+|{"|".join(_WORDS)})\s+{_UNIT}|(?:headcount|employees)[^.\d]{{0,20}}(\d+)', re.I)


def _counts(text):
    """Head-count style figures only; dates, years and periods are excluded."""
    text = _ISO.sub(' ', _QUARTER.sub(' ', str(text)))
    out = []
    for word, num in _COUNT.findall(text):
        token = (word or num).lower()
        out.append(_WORDS[token] if token in _WORDS else int(token))
    return out


def _scope_quantity(rows, up, verdict):
    claims = _claim_rows(rows)
    figs = []
    for r in _material(rows):
        nums = _counts(r.get('detail', ''))
        if nums:
            figs.append((r, nums))
    if len(figs) < 2:
        return ('Fewer than two exhibits state a head-count style figure. Gap: quantities cannot be reconciled; '
                'absence of a second figure is not agreement.', 'needs_evidence', _ids(claims or _material(rows)[:2]))
    distinct = sorted({n for _, nums in figs for n in nums})
    detail = '; '.join(f'{_rid(r)}={_short(nums, 3)}' for r, nums in figs)
    if len(distinct) > 1:
        return (f'Figures diverge across exhibits: {detail}. Gap: not shown to describe the same '
                'population or period.', 'needs_evidence', _ids([r for r, _ in figs]))
    return (f'Claim exhibits state the same figure ({distinct[0]}): {detail}. Gap: same figure does not prove '
            'same unit.', 'ready', _ids([r for r, _ in figs]))


def _scope_boundary(rows, up, verdict):
    claims = _claim_rows(rows) or _material(rows)
    found, silent = {}, []
    for r in claims:
        words = [w for w in _BOUNDARY if w in _text(r).lower()]
        if words:
            found[_rid(r)] = words
        else:
            silent.append(r)
    if not found:
        return ('No claim-bearing exhibit states an entity, unit or cohort boundary. Gap: scope of the claim '
                'is unresolved.', 'needs_evidence', _ids(claims))
    detail = '; '.join(f'{k}: {_short(v, 2)}' for k, v in found.items())
    note = f'Boundary terms stated: {detail}.'
    if silent:
        note += f' No boundary stated in {_short(_ids(silent))}.'
    return note, ('needs_evidence' if silent else 'ready'), _ids(claims)


def _events(rows):
    out = []
    for r in _material(rows):
        for d in _isodates(r.get('detail', '')):
            if d:
                out.append((d, r))
    return sorted(out, key=lambda x: (x[0], _rid(x[1])))


def _timing_event_order(rows, up, verdict):
    ev = _events(rows)
    ordered = [r for r in _material(rows) if re.search(r'\b(before|after|predat\w+|prior to|following)\b',
                                                      r.get('detail', ''), re.I)]
    if len({d for d, _ in ev}) < 2:
        note = 'Fewer than two distinct event dates in exhibit text. Gap: chronology cannot be built.'
        if ordered:
            note += f' Ordering is asserted without a dated anchor in {_short(_ids(ordered))}.'
        return note, 'needs_evidence', _ids(ordered or [r for _, r in ev] or _material(rows)[:2])
    chain = ' → '.join(f'{d} ({_rid(r)})' for d, r in ev[:4])
    note = f'Chronology: {chain}.'
    if ordered:
        note += f' Relative-order wording in {_short(_ids(ordered))} is checked against these dates only where both ends are dated.'
    return note, 'ready', _ids([r for _, r in ev] + ordered)


def _timing_lag(rows, up, verdict):
    ev = _events(rows)
    quarters = {}
    for r in _material(rows):
        for q, y in _QUARTER.findall(r.get('detail', '')):
            quarters.setdefault(f'Q{q} {y}', []).append(r)
    parts, refs = [], []
    if ev:
        lags = [((_asof(r) - d).days, r) for d, r in ev if _asof(r)]
        if lags:
            lag, r = max(lags, key=lambda x: x[0])
            parts.append(f'longest event-to-observation lag {lag} day(s) in {_rid(r)}')
            refs.append(_rid(r))
    if quarters:
        parts.append('periods named: ' + _short(quarters))
        refs += [_rid(r) for v in quarters.values() for r in v]
        if len(quarters) > 1:
            parts.append('periods differ across exhibits')
    if not parts:
        return ('No dated event or named period to measure. Gap: lag and period alignment are unknown.',
                'needs_evidence', _ids(_material(rows)[:2]))
    text = '; '.join(parts)
    return (text[0].upper() + text[1:] + '.',
            'needs_evidence' if len(quarters) > 1 else 'ready', refs)


def _material_relevance(rows, up, verdict):
    mat = _material(rows)
    thin = [r for r in mat if _GENERIC.search(str(r.get('detail', ''))) or len(str(r.get('detail', ''))) < 20]
    good = [r for r in mat if r not in thin and (re.search(r'\d', r.get('detail', '')) or r.get('claim'))]
    note = f'{len(good)} of {len(mat)} material exhibit(s) are specific (dated, counted or claim-bearing)'
    if thin:
        note += f'; generic: {_short(_ids(thin))}'
    return note + '.', ('ready' if good else 'needs_evidence'), _ids(good or mat)


def _material_tier(rows, up, verdict):
    mat = _material(rows)
    tiers = {}
    for r in mat:
        tiers.setdefault(_tier(r), []).append(r)
    order = ['primary record', 'provider reconstruction', 'self-asserted', 'rehearsal']
    note = 'Tiers: ' + ', '.join(f'{t} {len(tiers[t])}' for t in order if t in tiers) + '.'
    best = next((t for t in order if t in tiers), None)
    if best != 'primary record':
        return (note + ' Gap: no primary record present; reconstruction cannot stand in for one.',
                'needs_evidence', _ids(mat))
    return note, 'ready', _ids(tiers['primary record'])


def _challenge_alt(rows, up, verdict):
    claims = _claim_rows(rows) or _material(rows)
    for r in claims:
        for pattern, alt, test in _ALTERNATIVES:
            if re.search(pattern, _text(r), re.I):
                roots = {_root(x) for x in claims if not (_is_rehearsal(x) and 'replay' in str(x.get('source', '')).lower())}
                closed = len(roots) >= 2
                return (f'{r.get("source", "Source")} [{_rid(r)}] permits {alt}. Test: {test}. '
                        + ('Two or more independent roots limit this reading.' if closed
                           else 'Gap: only one root, so the alternative stays open.'),
                        'ready' if closed else 'needs_evidence', [_rid(r)])
    return ('No exhibit is specific enough to anchor an alternative explanation. Gap: counter-reading untested.',
            'needs_evidence', _ids(claims[:1]))


def _challenge_contrary(rows, up, verdict):
    mat = _material(rows)
    contrary = [r for r in mat if _BAD.search(r.get('detail', ''))]
    if contrary:
        return (f'Exhibit(s) {_short(_ids(contrary))} contain language that cuts against, narrows or '
                'qualifies the claim. Reviewer should read them before relying on the verdict.',
                'ready', _ids(contrary))
    return ('No supplied exhibit contradicts the claim. Gap: this is absence of contrary evidence, '
            'not corroboration.', 'ready', _ids(_claim_rows(rows) or mat[:1]))


def _challenge_timing(rows, up, verdict):
    mat = _material(rows)
    stamps = {str(r.get('as_of'))[:10] for r in mat if r.get('as_of')}
    ev = _events(rows)
    if len(stamps) == 1 and mat:
        return (f'Every exhibit is stamped {next(iter(stamps))}, so as_of shows retrieval date, not event date. '
                + (f'Event dates come only from text ({_short([_rid(r) for _, r in ev])}).' if ev
                   else 'Gap: no event date in text either, so the sequence is unverified.'),
                'ready' if ev else 'needs_evidence', _ids([r for _, r in ev] or mat[:2]))
    if not ev:
        return ('Observation dates vary but no event date appears in text. Gap: cannot separate event from '
                'collection timing.', 'needs_evidence', _ids(mat[:2]))
    return ('Observation dates vary and event dates are cited in text '
            f'({_short([_rid(r) for _, r in ev])}); a coincidental sequence cannot be excluded without a second source.',
            'ready', _ids([r for _, r in ev]))


def _challenge_sample(rows, up, verdict):
    mat = _material(rows)
    counts, thin = [], []
    for r in mat:
        for n in _counts(r.get('detail', '')):
            counts.append((n, r))
            if n < 20:
                thin.append(r)
    if re.search(r'suppress', ' '.join(r.get('detail', '') for r in mat), re.I):
        sup = [r for r in mat if 'suppress' in r.get('detail', '').lower()]
        thin += sup
    if not counts and not thin:
        return ('No cohort count is quoted. Gap: the sample behind any aggregate statement is unknown.',
                'needs_evidence', _ids(mat[:2]))
    if thin:
        return (f'Small or suppressed counts in {_short(_ids(thin))}. Gap: a cohort this size may not support the '
                'conclusion alone.', 'needs_evidence', _ids(thin))
    return (f'Counts quoted: {_short([f"{n} ({_rid(r)})" for n, r in counts])}; none below 20. '
            'Gap: denominators are not stated.', 'ready', _ids([r for _, r in counts]))


def _gaps_unavailable(rows, up, verdict):
    mat = _material(rows)
    off = [r for r in rows if r.get('id') and r not in mat]
    supp = [r for r in mat if re.search(r'suppress|unavailable|no company matched|not return', r.get('detail', ''), re.I)]
    if off or supp:
        names = [f'{r.get("label", "exhibit")} ({r.get("status", "limited")})' for r in off + supp]
        return (f'{len(off) + len(supp)} exhibit(s) limited: {_short(names)}. Each contributes no finding; '
                'the claim should not be read as cleared by them.', 'needs_evidence', _ids(off + supp))
    return ('All supplied exhibits returned usable content. Gap: sources never requested are not covered here.',
            'ready', _ids(mat))


def _gaps_corroboration(rows, up, verdict):
    mat = _material(rows)
    claims = {}
    for r in _claim_rows(rows):
        claims.setdefault(str(r['claim']), []).append(r)
    classes = {_tier(r) for r in mat if _tier(r) != 'rehearsal'}
    absent = [c for c in ('primary record', 'provider reconstruction', 'self-asserted') if c not in classes]
    if not claims:
        return ('No exhibit is tagged with a claim, so corroboration cannot be assessed per claim. Gap classes: '
                + _short(absent or ['none']) + '.', 'needs_evidence', _ids(mat[:2]))
    thin = [k for k, v in claims.items() if len({_tier(r) for r in v}) < 2 and len({_root(r) for r in v}) < 2]
    note = f'{len(claims)} claim(s); {len(thin)} rest on one source class.'
    if absent:
        note += f' Classes absent: {_short(absent)}.'
    return note, ('needs_evidence' if thin else 'ready'), _ids([r for v in claims.values() for r in v])


def _fresh_upstream(up):
    open_ = [u for u in up if u.get('status') != 'complete' or u.get('assessment') == 'needs_evidence']
    return open_


def _partner_agreement(rows, up, verdict):
    if not up:
        return ('No completed challenger report to map. Gap: agreement cannot be assessed.', 'needs_evidence', [])
    open_ = _fresh_upstream(up)
    refs = [ref for u in up for ref in u.get('refs', [])]
    agree = [u.get('name') or u.get('agent_id') for u in up if u not in open_]
    note = f'{len(agree)} of {len(up)} upstream report(s) closed: {_short(agree) or "none"}.'
    if open_:
        note += f' Still open: {_short([u.get("name") or u.get("agent_id") for u in open_])}.'
    return note, ('needs_evidence' if open_ else 'ready'), refs or _ids(_claim_rows(rows))


def _partner_questions(rows, up, verdict):
    qs, refs = [], []
    mat = _material(rows)
    off = [r for r in rows if r.get('id') and r not in mat]
    claims = _claim_rows(rows)
    roots = {_root(r) for r in claims if 'replay' not in str(r.get('source', '')).lower()}
    if len(roots) < 2 and claims:
        qs.append(f'Is there a second independent source for {_rid(claims[0])}?')
        refs.append(_rid(claims[0]))
    if off:
        qs.append(f'Can {off[0].get("label", "the unavailable exhibit")} be re-collected ({_rid(off[0])})?')
        refs.append(_rid(off[0]))
    ev = _events(rows)
    if ev:
        qs.append(f'Does the event date in {_rid(ev[0][1])} match the record held by the counterparty?')
        refs.append(_rid(ev[0][1]))
    for u in _fresh_upstream(up)[:2]:
        qs.append(f'What closes the concern raised by {u.get("name") or u.get("agent_id")}?')
    if not qs:
        return ('No open question arises from the supplied exhibits. Gap: reviewer judgement is still required.',
                'ready', _ids(mat[:1]))
    return 'Questions: ' + ' '.join(f'({i}) {q}' for i, q in enumerate(qs[:3], 1)), 'needs_evidence', refs or _ids(mat[:1])


def _authority_integrity(rows, up, verdict):
    mat = _material(rows)
    if not str(verdict or '').strip():
        return ('No proposed verdict supplied. Gap: nothing to preserve.', 'needs_evidence', _ids(mat[:1]))
    backing = _claim_rows(rows) or mat
    return (f'Proposed verdict "{str(verdict)[:60]}" is carried verbatim; it was not recomputed here. '
            f'{len(backing)} material exhibit(s) are available as support.', 'ready' if backing else 'needs_evidence',
            _ids(backing))


def _authority_trace(rows, up, verdict):
    claims = _claim_rows(rows)
    if not claims:
        return ('No exhibit carries a claim tag, so the verdict cannot be traced to specific exhibits.',
                'needs_evidence', _ids(_material(rows)[:2]))
    weak = [r for r in claims if _is_rehearsal(r) or not r.get('as_of')]
    note = f'Verdict traces to {len(claims)} claim exhibit(s): {_short(_ids(claims))}.'
    if weak:
        note += f' Rehearsal or undated: {_short(_ids(weak))}.'
    return note, 'ready' if not [r for r in weak if not r.get('as_of')] else 'needs_evidence', _ids(claims)


def _handoff_index(rows, up, verdict):
    cited = {ref for u in up for ref in u.get('refs', [])}
    all_ids = _ids(rows)
    orphan = [i for i in all_ids if i not in cited]
    known = set(all_ids)
    dangling = [c for c in cited if c not in known]
    line = ', '.join(f'{u.get("agent_id")}:{u.get("assessment") or u.get("status")}' for u in up[:4]) or 'none'
    note = f'{len(up)} upstream report(s) indexed ({line}). Uncited exhibits: {_short(orphan) or "none"}.'
    if dangling:
        note += f' Unknown ids cited: {_short(dangling)}.'
    return note, ('needs_evidence' if dangling else 'ready'), list(cited & known) or all_ids[:1]


def _handoff_open(rows, up, verdict):
    items, refs = [], []
    off = [r for r in rows if r.get('id') and r not in _material(rows)]
    if off:
        items.append(f'{len(off)} unavailable exhibit(s)')
        refs += _ids(off)
    open_ = _fresh_upstream(up)
    if open_:
        items.append('open upstream: ' + _short([u.get('name') or u.get('agent_id') for u in open_]))
        refs += [ref for u in open_ for ref in u.get('refs', [])]
    mode = {str(r.get('mode', '')).upper() for r in _material(rows)}
    rehearsal = mode & {'DEMO', 'REPLAY'}
    if rehearsal:
        items.append('exhibits are ' + '/'.join(sorted(rehearsal)) + ' material, not live records')
    refs = refs or _ids(_material(rows)[:1])
    if not items:
        return 'No open items from the supplied exhibits. Gap: reviewer sign-off still required.', 'ready', refs
    return 'Open: ' + '; '.join(items) + '.', ('needs_evidence' if off or open_ else 'ready'), refs


_CHECKS = {
    'identity.registry_match': _identity_registry_match,
    'identity.alias_collision': _identity_alias_collision,
    'sources.provenance': _sources_provenance,
    'sources.independence': _sources_independence,
    'dates.recency': _dates_recency,
    'dates.sequence': _dates_sequence,
    'scope.quantity_reconciliation': _scope_quantity,
    'scope.entity_boundary': _scope_boundary,
    'timing.event_order': _timing_event_order,
    'timing.lag_window': _timing_lag,
    'material.relevance': _material_relevance,
    'material.source_tier': _material_tier,
    'challenge.alt_explanation': _challenge_alt,
    'challenge.contrary_evidence': _challenge_contrary,
    'challenge.timing_alternative': _challenge_timing,
    'challenge.sample_size': _challenge_sample,
    'gaps.unavailable_sources': _gaps_unavailable,
    'gaps.missing_corroboration': _gaps_corroboration,
    'partner.agreement_map': _partner_agreement,
    'partner.reviewer_questions': _partner_questions,
    'authority.verdict_integrity': _authority_integrity,
    'authority.evidence_trace': _authority_trace,
    'handoff.receipt_index': _handoff_index,
    'handoff.open_items': _handoff_open,
}
_GATED = {'scope', 'timing', 'challenge', 'partner'}
_CAVEAT = _GATED - {'partner'}


def demo_specialist(spec, rows, upstream, verdict):
    """Run the deterministic local check for one specialist.

    Returns ``{note, assessment, refs}``. Refs are always ids present in ``rows``;
    an empty citation set forces ``needs_evidence``.
    """
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    upstream = [u for u in (upstream or []) if isinstance(u, dict)]
    check = _CHECKS.get(spec.get('id'))
    if check is None:
        return dict(note='No local check is defined for this specialist.', assessment='needs_evidence', refs=[])
    note, assessment, refs = check(rows, upstream, verdict)
    if spec['id'].split('.')[0] in _CAVEAT:
        note += _caveat(upstream)
    return _result(note, assessment, refs, rows, upstream, gate=spec['id'].split('.')[0] in _GATED)
