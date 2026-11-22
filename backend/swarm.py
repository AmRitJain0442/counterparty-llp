"""Case-local dependency graph for bounded council observations.

Notes are advisory; the supplied deterministic verdict is never recomputed.
"""
from concurrent.futures import ThreadPoolExecutor
from .drafting import draft_note


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


def agents_for(desk):
    return [dict(id=key, name=name, group=group, task=f'{desk}: {task}', lane=lane)
            for key, name, group, task, lane in _SPECS]


def run_council(desk, evidence, verdict, emit, mode):
    """Run parallel stages, emitting serialized events with completed dependencies.

    All runtime state belongs to this invocation. Live model failures remain visible
    and block downstream model work rather than producing synthetic live notes.
    """
    if mode not in ('demo', 'live', 'replay'):
        raise ValueError('mode must be demo, replay, or live')
    replay = mode != 'live'
    rows = [dict(row) for row in evidence if row.get('id')]
    material = [r for r in rows if r.get('status', 'ok') not in
                ('unavailable', 'error', 'failed') and (r.get('detail') or r.get('label'))]
    reports = {}
    agents = {a['id']: a for a in agents_for(desk)}
    stages = [ [('identity', []), ('sources', []), ('dates', []), ('material', []), ('gaps', [])],
               [('analyst_scope', ['identity', 'sources', 'material']),
                ('analyst_timing', ['dates', 'sources', 'material'])],
               [('challenger_scope', ['analyst_scope', 'analyst_timing']),
                ('challenger_timing', ['analyst_scope', 'analyst_timing'])],
               [('partner', ['challenger_scope', 'challenger_timing']),
                ('authority', ['material'])],
               [('handoff', ['partner', 'authority', 'gaps'])] ]

    def work(key, deps):
        agent = agents[key]
        selected = material
        if key == 'dates':
            selected = [r for r in material if r.get('as_of')]
        elif key == 'gaps':
            selected = [r for r in rows if r not in material]
        refs = list(dict.fromkeys(r['id'] for r in selected))
        status = 'complete'
        if key.startswith(('analyst_', 'challenger_')) or key == 'partner':
            upstream = [reports[d] for d in deps]
            if any(r['status'] != 'complete' for r in upstream):
                detail, status = 'Required council output unavailable; review blocked.', 'blocked'
            elif replay:
                observations = '; '.join(str(r.get('detail') or r.get('label'))[:400] for r in selected)
                detail = f'Replay : {agent["task"]}. Curated observations: {observations}. '
                detail += 'Review inputs: ' + ', '.join(deps) + '. Deterministic verdict remains authoritative.'
            else:
                context = [dict(id=r['id'], label=r.get('label', ''),
                                detail=r.get('detail', ''), as_of=r.get('as_of', ''),
                                source=r.get('source', '')) for r in selected]
                context += [dict(label=f'Dependency {r["agent_id"]}', detail=r['detail'],
                                 source=', '.join(r['refs'])) for r in upstream]
                context.insert(0, dict(label='Bounded assignment', detail=agent['task'], source='Council'))
                detail, status = draft_note(desk, context, verdict,
                                           'counsel' if key.startswith('challenger') else 'analyst')
                if not detail:
                    detail = f'Vertex note unavailable: {status}'
                    status = 'unavailable'
        elif key == 'authority':
            detail = f'Authoritative deterministic adjudication: {verdict}'
        elif key == 'handoff':
            detail = 'Review outputs: ' + ', '.join(deps)
        else:
            detail = f'{agent["task"]}: {len(selected)} observations; sources: ' + ', '.join(
                dict.fromkeys(str(r.get('source', 'unknown')) for r in selected))
        return dict(agent_id=key, name=agent['name'], group=agent['group'], status=status,
                    detail=detail, refs=refs, depends_on=list(deps))

    with ThreadPoolExecutor(max_workers=5) as pool:
        for stage in stages:
            pending = []
            for key, deps in stage:
                emit(dict(event='start', agent_id=key, status='running', depends_on=deps,
                          mode='replay' if replay else 'live', replay=replay))
                pending.append((key, pool.submit(work, key, deps)))
            for key, future in pending:
                try:
                    result = future.result()
                except Exception as exc:
                    a = agents[key]
                    result = dict(agent_id=key, name=a['name'], group=a['group'],
                                  status='unavailable', detail=f'Council task failed: {type(exc).__name__}',
                                  refs=[], depends_on=next(d for k, d in stage if k == key))
                reports[key] = result
                emit(dict(event='end', **result, mode='replay' if replay else 'live', replay=replay))
    return [reports[a['id']] for a in agents_for(desk)]
