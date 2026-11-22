from threading import Barrier
from backend import swarm

ROWS = [dict(id='e1', label='Claim', detail='Dated observation', source='Registry', as_of='2026-01-01')]


def test_roster_and_replay_dependencies():
    agents = swarm.agents_for('payment')
    assert len(agents) == len({a['id'] for a in agents}) == 12
    assert set(a['group'] for a in agents) == {'identity', 'discovery', 'challenge', 'decision'}
    events = []
    reports = swarm.run_council('payment', ROWS, 'HELD', events.append, 'demo')
    ended = set()
    for event in events:
        assert event['replay'] and event['mode'] == 'replay'
        assert set(event['depends_on']) <= ended
        if event['event'] == 'end':
            ended.add(event['agent_id'])
    assert len(events) == 24
    assert all(r['refs'] == ['e1'] for r in reports if r['agent_id'] != 'gaps')
    assert 'HELD' in next(r['detail'] for r in reports if r['agent_id'] == 'authority')


def test_live_parallel_fanout_and_context(monkeypatch):
    analyst = Barrier(2)
    challenger = Barrier(2)
    calls = []

    def note(desk, evidence, verdict, role):
        task = evidence[0]['detail']
        calls.append(evidence)
        if 'Assess' in task:
            analyst.wait(timeout=3)
        elif 'Challenge' in task:
            challenger.wait(timeout=3)
        return task, 'complete'

    monkeypatch.setattr(swarm, 'draft_note', note)
    reports = swarm.run_council('payment', ROWS, 'HELD', lambda e: None, 'live')
    assert len(calls) == 5
    assert all(r['status'] == 'complete' for r in reports)
    partner = calls[-1]
    assert {r['label'] for r in partner} >= {'Dependency challenger_scope', 'Dependency challenger_timing'}


def test_live_missing_vertex_is_honest(monkeypatch):
    monkeypatch.setattr(swarm, 'draft_note', lambda *a: (None, 'unconfigured'))
    reports = {r['agent_id']: r for r in swarm.run_council('payment', ROWS, 'HELD', lambda e: None, 'live')}
    assert reports['analyst_scope']['status'] == 'unavailable'
    assert reports['partner']['status'] == 'blocked'
    assert reports['authority']['status'] == 'complete'

