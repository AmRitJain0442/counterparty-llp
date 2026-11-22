import re
from backend import demo, personas, swarm

SPECS = [s for pid in personas.SPECIALISTS for s in personas.SPECIALISTS[pid]]
PARENTS = {a['id'] for a in swarm.agents_for('payment') if not a['parent_id']}


def test_roster_is_complete_and_distinct():
    assert set(personas.PARENT_PERSONAS) == set(personas.SPECIALISTS) == PARENTS
    assert len(PARENTS) == 12 and len(SPECS) == 24
    assert all(len(v) == 2 for v in personas.SPECIALISTS.values())
    assert len({s['id'] for s in SPECS}) == 24
    texts = [*personas.PARENT_PERSONAS.values(), *(s['persona'] for s in SPECS)]
    assert len(set(texts)) == len(texts)
    assert all(set(s) == {'id', 'name', 'persona', 'task'} and all(s.values()) for s in SPECS)
    assert {s['id'] for s in SPECS} == set(personas._CHECKS)


def test_demo_checks_cite_only_supplied_rows_for_every_case():
    for desk in demo.CASES:
        rows = demo.build_demo(desk)['evidence']
        ids = {r['id'] for r in rows}
        for spec in SPECS:
            out = personas.check_specialist(spec, rows, [], 'HELD')
            assert set(out) == {'note', 'assessment', 'refs'}
            assert out['assessment'] in ('ready', 'needs_evidence')
            assert set(out['refs']) <= ids and 0 < len(out['note']) <= 700
            assert out['refs'] or out['assessment'] == 'needs_evidence'


def test_checks_differ_and_report_gaps():
    rows = demo.build_demo('candidate')['evidence']
    notes = {s['id']: personas.check_specialist(s, rows, [], 'HELD')['note'] for s in SPECS}
    assert len(set(notes.values())) == len(notes)
    assert 'diverge' in notes['scope.quantity_reconciliation'] and '40' in notes['scope.quantity_reconciliation']
    empty = personas.check_specialist(personas.SPECIALISTS['gaps'][0], [], [], 'HELD')
    assert empty['assessment'] == 'needs_evidence' and empty['refs'] == []


def test_no_false_corroboration_from_a_single_root_or_replay():
    row = dict(id='a', source='Crustdata', label='x', detail='Observed 3 profiles.', as_of='2026-01-01',
               mode='LIVE', url='https://crustdata.com/x', claim='c')
    replay = dict(row, id='b', source='Watch replay', mode='REPLAY', url=None)
    out = personas.check_specialist(personas.SPECIALISTS['sources'][1], [row, replay], [], 'HELD')
    assert out['assessment'] == 'needs_evidence' and '1 independent root' in out['note']
    unavailable = dict(row, id='c', status='error')
    gap = personas.check_specialist(personas.SPECIALISTS['gaps'][0], [row, unavailable], [], 'HELD')
    assert gap['assessment'] == 'needs_evidence' and gap['refs'] == ['c']


def test_upstream_incomplete_blocks_a_ready_result():
    rows = demo.build_demo('payment')['evidence']
    blocked = [dict(agent_id='analyst_scope', name='Scope analyst', status='blocked', assessment=None, refs=[])]
    out = personas.check_specialist(personas.SPECIALISTS['challenger_scope'][1], rows, blocked, 'HELD')
    assert out['assessment'] == 'needs_evidence' and 'Scope analyst' in out['note']


def test_no_personal_detail_in_persona_text():
    blob = ' '.join([*personas.PARENT_PERSONAS.values(), *(s['persona'] + s['task'] for s in SPECS)])
    assert not re.search(r'@|https?://|\d{4}-\d{2}-\d{2}', blob)


def test_calendar_check_compares_dates_against_the_card_observation():
    spec = next(s for s in SPECS if s['id'] == 'dates.sequence')
    row = dict(id='headcount', detail='47 profiles on 2026-11-02.', as_of='2026-11-22T11:28:43Z')
    earlier = personas.check_specialist(spec, [row], [], 'INSUFFICIENT WITNESSES')
    assert earlier['assessment'] == 'ready' and earlier['refs'] == ['headcount']
    assert 'none is later' in earlier['note']
    for as_of in ('2026-10-22', ''):
        result = personas.check_specialist(spec, [dict(row, as_of=as_of)], [], 'INSUFFICIENT WITNESSES')
        assert result['assessment'] == 'needs_evidence' and result['refs'] == ['headcount']
