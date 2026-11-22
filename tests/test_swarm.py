from threading import Barrier
from backend import swarm

ROWS = [dict(id='e1', label='Claim', detail='Dated observation', source='Registry', as_of='2026-01-01')]


def test_roster_and_live_dependencies(monkeypatch):
    monkeypatch.setattr(swarm, 'draft_note', lambda *a, **kw: ({'note': 'Reviewed.', 'assessment': 'ready', 'refs': ['e1']}, 'complete'))
    agents = swarm.agents_for('payment')
    assert len(agents) == len({a['id'] for a in agents}) == 36
    assert set(a['group'] for a in agents) == {'identity', 'discovery', 'challenge', 'decision'}
    events = []
    reports = swarm.run_council('payment', ROWS, 'HELD', events.append, 'live')
    ended = set()
    for event in events:
        assert not event['replay'] and event['mode'] == 'live'
        assert set(event['depends_on']) <= ended
        if event['event'] == 'end':
            ended.add(event['agent_id'])
    assert len(events) == 72
    assert [r['agent_id'] for r in reports] == [a['id'] for a in agents]
    for a in agents[:12]:
        positions = {(e['agent_id'], e['event']): i for i, e in enumerate(events)}
        for child in a['specialist_ids']:
            assert positions[a['id'], 'start'] < positions[child, 'start'] < positions[child, 'end'] < positions[a['id'], 'end']
    assert 'HELD' in next(r['detail'] for r in reports if r['agent_id'] == 'authority')


def test_live_parallel_fanout_and_context(monkeypatch):
    analyst = Barrier(2)
    challenger = Barrier(2)
    calls = []
    specialists = set()

    def note(desk, evidence, verdict, role, **instructions):
        task = instructions['mandate']
        assert instructions['persona']
        assert any(r.get('id') == 'e1' for r in evidence)
        rationale = next(r for r in evidence if r['label'] == 'Evidence gate rationale')
        assert rationale['detail'] == 'The independent records agree.' and rationale['claim'] == 'Vendor domain'
        if role == 'specialist':
            specialists.add(instructions['persona'])
        calls.append(evidence)
        if task.startswith('payment: Assess'):
            analyst.wait(timeout=3)
        elif task.startswith('payment: Challenge'):
            challenger.wait(timeout=3)
        return {'note':task, 'assessment':'ready', 'refs':['e1']}, 'complete'

    monkeypatch.setattr(swarm, 'draft_note', note)
    reports = swarm.run_council('payment', ROWS, 'HELD', lambda e: None, 'live',
                                verdict_summary='The independent records agree.', proposition='Vendor domain')
    assert len(calls) == 28
    assert len(specialists) == 23
    assert all(r['status'] == 'complete' for r in reports)
    partner = next(c for c in calls if any(r.get('label') == 'Dependency challenger_scope' for r in c) and any(r.get('label') == 'Bounded assignment' for r in c))
    assert {r['label'] for r in partner} >= {'Dependency challenger_scope', 'Dependency challenger_timing'}


def test_live_missing_vertex_is_honest(monkeypatch):
    monkeypatch.setattr(swarm, 'draft_note', lambda *a, **kw: (None, 'unconfigured'))
    reports = {r['agent_id']: r for r in swarm.run_council('payment', ROWS, 'HELD', lambda e: None, 'live')}
    children = [r for r in reports.values() if r['parent_id']]
    assert len(children) == 24
    assert reports['dates.sequence']['status'] == 'complete'
    assert all(r['status'] == 'unavailable' and not r['refs'] for r in children if r['agent_id'] != 'dates.sequence')
    assert reports['analyst_scope']['status'] == 'blocked'
    assert reports['partner']['status'] == 'blocked'
    assert reports['authority']['status'] == 'complete'

