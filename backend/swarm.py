"""Case-local dependency graph for bounded council observations.

Notes are advisory; the supplied deterministic verdict is never recomputed.
"""
from concurrent.futures import ThreadPoolExecutor
from .drafting import draft_note
from .personas import PARENT_PERSONAS, SPECIALISTS, check_specialist
from threading import RLock


_SPECS = (
    ('identity', 'Identity resolver', 'identity', 'Check identity binding', 'identity'),
    ('sources', 'Source auditor', 'identity', 'List attributable sources', 'sources'),
    ('dates', 'Date auditor', 'identity', 'Check observation dates', 'dates'),
    ('analyst_scope', 'Scope analyst', 'discovery', 'Assess claim scope and corroboration', 'scope'),
    ('analyst_timing', 'Timing analyst', 'discovery', 'Assess chronology and source limitations', 'timing'),
    ('material', 'Material evidence clerk', 'discovery', 'Select material observations', 'material'),
    ('challenger_scope', 'Scope challenger', 'challenge', 'Challenge scope analyst assumptions', 'scope'),
    ('challenger_timing', 'Timing challenger', 'challenge', 'Challenge chronology and alternatives', 'timing'),
    ('gaps', 'Evidence gaps clerk', 'challenge', 'Identify unavailable evidence', 'gaps'),
    ('partner', 'Review partner', 'decision', 'Synthesize challenges for human follow-up', 'synthesis'),
    ('authority', 'Verdict custodian', 'decision', 'Preserve deterministic adjudication', 'authority'),
    ('handoff', 'Handoff clerk', 'decision', 'Index council outputs for review', 'handoff'),
)


_STAGES = [ [('identity', []), ('sources', []), ('dates', []), ('material', []), ('gaps', [])],
               [('analyst_scope', ['identity', 'sources', 'material']),
                ('analyst_timing', ['dates', 'sources', 'material'])],
               [('challenger_scope', ['analyst_scope', 'analyst_timing']),
                ('challenger_timing', ['analyst_scope', 'analyst_timing'])],
               [('partner', ['challenger_scope', 'challenger_timing']),
                ('authority', ['material'])],
               [('handoff', ['partner', 'authority', 'gaps'])] ]
_DEPENDENCIES = {key: deps for stage in _STAGES for key, deps in stage}


def agents_for(desk):
    leads = [dict(id=key, name=name, group=group, task=f'{desk}: {task}', lane=lane,
                  persona=PARENT_PERSONAS[key], parent_id=None,
                  specialist_ids=[s['id'] for s in SPECIALISTS[key]],
                  depends_on=list(_DEPENDENCIES[key]))
             for key, name, group, task, lane in _SPECS]
    children = [dict(id=s['id'], name=s['name'], group=a['group'], task=s['task'],
                     lane=a['lane'], persona=s['persona'], parent_id=a['id'],
                     specialist_ids=[], depends_on=a['depends_on'][:])
                for a in leads for s in SPECIALISTS[a['id']]]
    return leads + children


def run_council(desk, evidence, verdict, emit, mode, *, verdict_summary='', proposition=''):
    """Run parallel stages, emitting serialized events with completed dependencies.

    All runtime state belongs to this invocation. Live model failures remain visible
    and block downstream model work rather than producing synthetic live notes.
    """
    if mode not in ('demo', 'live', 'replay'):
        raise ValueError('mode must be demo, replay, or live')
    replay = mode != 'live'
    rows = [dict(row) for row in evidence if row.get('id')]
    material = [r for r in rows if r.get('status', 'ok') in ('ok', 'complete') and (r.get('detail') or r.get('label'))]
    reports = {}
    event_lock = RLock()
    sink = emit
    def emit(event):
        with event_lock:
            sink(event)
    agents = {a['id']: a for a in agents_for(desk)}
    decision_context = dict(label='Evidence gate rationale', detail=verdict_summary, claim=proposition or '',
                            source='Case adjudication')

    def work(key, deps):
        agent = agents[key]
        selected = material
        if key == 'dates':
            selected = [r for r in material if r.get('as_of')]
        elif key == 'gaps':
            selected = [r for r in rows if r not in material]
        refs = list(dict.fromkeys(r['id'] for r in selected))
        status = 'complete'
        assessment = None
        synthesizes = key.startswith(('analyst_', 'challenger_')) or key == 'partner'
        if synthesizes:
            upstream = [reports[d] for d in deps] + [reports[c] for c in agent["specialist_ids"]]
            if any(r['status'] != 'complete' for r in upstream):
                detail, status = 'Required council output unavailable; review blocked.', 'blocked'
            elif replay:
                observations = '; '.join(str(r.get('detail') or r.get('label'))[:400] for r in selected)
                detail = f'{agent["task"]}. Curated observations: {observations}. '
                detail += 'Reviewed inputs from ' + ', '.join(agents[d]['name'] for d in deps) + '.'
                assessment = 'rehearsal'
            else:
                dependencies = [dict(label=f'Dependency {r["agent_id"]}', detail=f"{r.get('assessment') or 'Observation'}: {r['detail']}",
                                 source=', '.join(r['refs'])) for r in upstream]
                context = [dict(label='Bounded assignment', detail=agent['task'], source='Council'), decision_context,
                           *dependencies, *rows]
                role = 'counsel' if key.startswith('challenger') else 'analyst'
                review, status = draft_note(desk, context, verdict, 'partner' if key == 'partner' else role, persona=agent['persona'], mandate=agent['task'])
                if review:
                    detail, assessment, refs = review['note'], review['assessment'], review['refs']
                else:
                    detail = f'Vertex note unavailable: {status}'
                    status = 'unavailable'
        elif key == 'authority':
            detail = f'Evidence gate produced the proposed finding {verdict}.'
        elif key == 'identity':
            identity_rows = [r for r in material if 'ident' in r.get('label','').lower() or 'match' in r.get('label','').lower()]
            detail = ('Identity exhibits: ' + ', '.join(r['label'] for r in identity_rows)
                      if identity_rows else 'No separate identity exhibit. Check the identity binding in the case records.')
        elif key == 'dates':
            dates = sorted({str(r['as_of'])[:10] for r in selected})
            detail = (f'Observation dates range from {dates[0]} to {dates[-1]}.' if dates
                      else 'No source card carries an observation date.')
        elif key == 'gaps':
            detail = ('Unavailable source cards: ' + ', '.join(r.get('label','Unknown') for r in selected)
                      if selected else 'All supplied source cards were available.')
        elif key == 'material':
            detail = 'Available source cards: ' + (', '.join(r.get('label','Unknown') for r in selected) or 'none')
        elif key == 'handoff':
            detail = 'Filed work from ' + ', '.join(agents[d]['name'] for d in deps) + '.'
        else:
            detail = f'{agent["task"]}: {len(selected)} observations; sources: ' + ', '.join(
                dict.fromkeys(str(r.get('source', 'unknown')) for r in selected))
        children = [reports[c] for c in agent['specialist_ids']]
        if not synthesizes or replay:
            detail += ' Specialist observations: ' + ' '.join(
                f"{child['name']}: {child['detail']}" for child in children)
            refs = list(dict.fromkeys(refs + [ref for c in children for ref in c['refs']]))
        if status != 'complete':
            refs = []
        if any(c['status'] != 'complete' or c.get('assessment') == 'needs_evidence' for c in children):
            assessment = 'needs_evidence'
        return dict(agent_id=key, name=agent['name'], group=agent['group'], status=status,
                    detail=detail, refs=refs, assessment=assessment, depends_on=list(deps),
                    persona=agent['persona'], parent_id=None, specialist_ids=agent['specialist_ids'])

    def event(kind, agent, **extra):
        emit(dict(event=kind, agent_id=agent['id'], name=agent['name'], group=agent['group'],
                  depends_on=agent['depends_on'], parent_id=agent['parent_id'],
                  persona=agent['persona'], specialist_ids=agent['specialist_ids'],
                  mode='replay' if replay else 'live', replay=replay, **extra))

    def failure(agent, exc):
        return dict(agent_id=agent['id'], name=agent['name'], group=agent['group'],
                    detail=f'Council task unavailable: {exc}', refs=[], status='unavailable',
                    assessment='needs_evidence', parent_id=agent['parent_id'],
                    persona=agent['persona'], depends_on=agent['depends_on'],
                    specialist_ids=agent['specialist_ids'])

    def child_work(spec):
        agent = agents[spec['id']]
        event('start', agent, detail=agent['task'], status='running')
        try:
            upstream = [reports[d] for d in agent['depends_on']]
            if replay or agent['id'] == 'dates.sequence':
                review = check_specialist(spec, rows, upstream, verdict)
                status = 'complete'
            else:
                dependencies = [dict(label=f"Dependency {r['agent_id']}",
                                 detail=f"{r['status']} / {r.get('assessment')}: {r['detail']}",
                                 source=', '.join(r['refs'])) for r in upstream]
                review, status = draft_note(desk, [decision_context, *dependencies, *rows], verdict, 'specialist',
                                            persona=spec['persona'], mandate=spec['task'])
            if review is None:
                result = failure(agent, status)
            else:
                result = dict(failure(agent, ''), detail=review['note'], refs=review['refs'],
                              assessment=review['assessment'], status=status)
        except Exception as exc:
            result = failure(agent, type(exc).__name__)
        reports[agent['id']] = result
        event('end', agent, **{k:v for k,v in result.items() if k not in
              ('agent_id','name','group','depends_on','parent_id','persona','specialist_ids')})
        return result

    # Separate executors: waiting leads cannot occupy a child's execution slot.
    with ThreadPoolExecutor(max_workers=6) as children, ThreadPoolExecutor(max_workers=5) as leads:
        def parent_work(key, deps):
            agent = agents[key]
            event('start', agent, detail=agent['task'], status='running')
            futures = [children.submit(child_work, spec) for spec in SPECIALISTS[key]]
            for future in futures:
                future.result()
            try:
                result = work(key, deps)
            except Exception as exc:
                result = failure(agent, type(exc).__name__)
            reports[key] = result
            event('end', agent, **{k:v for k,v in result.items() if k not in
                  ('agent_id','name','group','depends_on','parent_id','persona','specialist_ids')})
        for stage in _STAGES:
            futures = [leads.submit(parent_work, key, deps) for key, deps in stage]
            for future in futures:
                future.result()
    return [reports[a['id']] for a in agents_for(desk)]
