import { useEffect, useMemo, useRef, useState } from 'react'
import { DESKS, DESK_BY_ID, subjectSpec, executiveProblem } from '../desks'
import { formatCredits } from '../format'
import './inspector.css'

const GROUPS = [
  ['identity', 'Identity', 'Resolve who or what the subject is'],
  ['discovery', 'Discovery', 'Collect dated witnesses'],
  ['challenge', 'Challenge', 'Test competing explanations'],
  ['decision', 'Decision', 'Reconcile findings and file the case'],
]
const STATUS_LABEL = { idle: 'Idle', queued: 'Queued', running: 'Running', done: 'Done', complete: 'Done', ok: 'Done', error: 'Failed', failed: 'Failed', blocked: 'Blocked', held: 'Held', unavailable: 'Unavailable' }

const norm = s => String(s || 'idle').toLowerCase()
const statusClass = s => {
  const n = norm(s)
  if (n === 'running') return 'run'
  if (['done', 'complete', 'ok'].includes(n)) return 'ok'
  if (['error', 'failed', 'blocked', 'unavailable'].includes(n)) return 'bad'
  return 'idle'
}
const label = s => STATUS_LABEL[norm(s)] || String(s)
const optId = o => (typeof o === 'string' ? o : o.id ?? o.value ?? o.key)
const optName = o => (typeof o === 'string' ? o : o.label ?? o.name ?? o.title ?? String(optId(o)))

export default function Inspector({
  desk, agent, agents = [], events = [], onSelect, onClose, onRun, running, record,
  subject = '', setSubject, inputs = {}, setInputs, consent = false, setConsent, onDesk, caseOptions = [], onCase, error,
  section, setSection, onReplay, replaying,
}) {
  const spec = DESK_BY_ID[desk] || DESKS[0]
  const [open, setOpen] = useState({})
  const body = useRef(null)
  useEffect(() => { body.current?.scrollTo(0, 0) }, [section, agent?.id, desk])

  const latest = useMemo(() => {
    const m = {}
    for (const e of events) m[e.agent_id] = e
    return m
  }, [events])
  const byGroup = useMemo(() => {
    const m = {}
    for (const [g] of GROUPS) m[g] = agents.filter(a => a.group === g && !a.parent_id)
    return m
  }, [agents])

  const children = agents.filter(a => a.parent_id)
  const team = children.filter(a => a.parent_id === agent?.id)
  const parent = agents.find(a => a.id === agent?.parent_id)
  const role = parent ? 'Specialist' : team.length ? 'Lead' : 'Agent'
  const upstream = agents.filter(a => agent?.depends_on?.includes(a.id))
  const downstream = agents.filter(a => !a.parent_id && a.depends_on?.includes(agent?.id))
  const reports = useMemo(()=>Object.fromEntries((record?.swarm_reports || []).map(r=>[r.agent_id,r])),[record])
  const finding = id => latest[id]?.event === 'end' ? reports[id] || latest[id] : !replaying ? reports[id] : null
  const status = id => latest[id]?.status || finding(id)?.status
  const report = agent && finding(agent.id)
  const recent = events.slice(-8).reverse()
  const needsConsent = spec.alwaysConsent || spec.consentFor?.some(k => (inputs[k] || '').trim())
  const rosterOpen = g => open[g] ?? (agent ? agent.group === g : g === 'identity')
  const subjectText = subjectSpec(spec)
  const execProblem = desk === 'company' ? executiveProblem(inputs) : ''
  const missing = !!execProblem || !subject.trim() || spec.fields.some(f => f.required && !(inputs[f.key] || '').trim()) || (needsConsent && !consent)

  const submit = e => { e.preventDefault(); if (!running && !missing) onRun?.() }
  const rosterButton = a => (
    <button type="button" className={agent?.id === a.id ? 'on' : ''} aria-pressed={agent?.id === a.id} onClick={() => onSelect?.(a.id)}>
      <span>{a.name}</span><span className={`insp-st ${statusClass(status(a.id))}`}>{label(status(a.id))}</span>
    </button>
  )

  return (
    <aside className="insp" style={{ '--desk': spec.color }} aria-label="Agent inspector">
      <header className="insp-head">
        <div className="insp-title"><span>{section === 'agents' && agent ? role+' · '+agent.group+' swarm' : 'Investigation desk'}</span>
          <b>{section === 'agents' && agent ? agent.name : spec.name + ' investigation'}</b></div>
        <button type="button" className="insp-x" onClick={onClose} aria-label="Close inspector">×</button>
      </header>
      <nav className="insp-tabs" aria-label="Inspector sections">
        {['agents','run','trace'].map(t => <button key={t} type="button" aria-current={section === t ? 'page' : undefined}
          onClick={() => setSection(t)}>{t === 'agents' ? 'Agents' : t === 'run' ? 'Run' : 'Trace'}</button>)}
      </nav>
      <div className="insp-body" ref={body}>
        {error && <p className="insp-err" role="alert">{error}</p>}
        {section !== 'trace' && <>
        <div className="insp-desks" role="tablist" aria-label="Desk">
          {DESKS.map(d => (
            <button key={d.id} type="button" role="tab" aria-selected={d.id === desk} style={{ '--c': d.color }}
              disabled={running} className={d.id === desk ? 'on' : ''} onClick={() => onDesk?.(d.id)}>{d.name}</button>
          ))}
        </div>
        <p className="insp-q">{spec.question}</p></>}

        {section === 'agents' && <>
        {agent && <section className="insp-sec">
          <h3>Assignment</h3>
          {agent.persona && <p className="insp-persona">{agent.persona}</p>}
          {agent.task && <p>{agent.task.replace(/^[^:]+: /,'')}</p>}
          <dl className="insp-facts">
            {parent && <div><dt>Lead</dt><dd><button className="insp-parent" onClick={()=>onSelect(parent.id)}>{parent.name} ↗</button></dd></div>}
            <div><dt>Receives from</dt><dd>{upstream.map(a=>a.name).join(', ') || 'Case evidence'}</dd></div>
            <div><dt>Hands off to</dt><dd>{parent?.name || downstream.map(a=>a.name).join(', ') || 'Case ledger'}</dd></div>
            <div><dt>Status</dt><dd>{label(status(agent.id))}</dd></div>
          </dl>
          {team.length>0 && <section className="insp-team"><h4>Specialist reports</h4>
            {team.map(child=><div key={child.id}>
              <button onClick={()=>onSelect(child.id)}>
                <strong>{child.name}</strong><small>{label(status(child.id))} ↗</small>
                {child.persona && <span>{child.persona}</span>}
              </button>
              {finding(child.id) && <details><summary>{child.name} finding</summary><p>{finding(child.id).detail}</p></details>}
            </div>)}
          </section>}
          {report && <section className="agent-report"><h4>{role} finding</h4><p>{report.detail}</p>
            {report.assessment && <p>Assessment · {report.assessment.replaceAll('_',' ')}</p>}
            {report.refs?.map(id => {
              const row = record?.evidence?.find(e=>e.id===id)
              return row ? <details key={id}><summary>{row.label} · {row.source}</summary><p>{row.detail}</p><small>{row.as_of}</small></details> : <small className="insp-ref" key={id}>{id}</small>
            })}</section>}
        </section>}
        <section className="insp-sec">
          <h3>Swarm roster <span>{children.length ? (agents.length-children.length)+' leads + '+children.length+' specialists' : agents.length+' agents'}</span></h3>
          {GROUPS.map(([g, name, hint]) => (
            <div key={g} className="insp-acc">
              <button type="button" aria-expanded={rosterOpen(g)} onClick={() => setOpen({ ...open, [g]: !rosterOpen(g) })}>
                <span>{name}<small>{hint}</small></span><em>{byGroup[g].length} {children.length?'leads':'agents'}</em>
              </button>
              {rosterOpen(g) && (
                <ul>
                  {byGroup[g].length === 0 && <li className="insp-empty">No agents in this group</li>}
                  {byGroup[g].map(a => (
                    <li key={a.id}>
                      {rosterButton(a)}
                      {children.some(c=>c.parent_id===a.id) && <ul className="insp-specialists" aria-label={a.name+' specialists'}>
                        {children.filter(c=>c.parent_id===a.id).map(c=><li key={c.id}>{rosterButton(c)}</li>)}
                      </ul>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </section>

        </>}
        {section === 'run' && <form className="insp-sec insp-form" onSubmit={submit}>
          <h3>Live investigation</h3>
          <label className="insp-f"><span>{subjectText.label}</span>
            <input value={subject} maxLength={180} required onChange={e => setSubject?.(e.target.value)}
              placeholder={subjectText.placeholder} />
          </label>

          {spec.fields.map(f => (
            <label key={f.key} className="insp-f"><span>{f.label}{f.required ? '' : ' (optional)'}</span>
              {f.long
                ? <textarea rows={3} value={inputs[f.key] || ''} required={f.required} placeholder={f.placeholder} onChange={e => setInputs?.({ ...inputs, [f.key]: e.target.value })} />
                : <input value={inputs[f.key] || ''} required={f.required} placeholder={f.placeholder} onChange={e => setInputs?.({ ...inputs, [f.key]: e.target.value })}
                    aria-invalid={f.key === 'executive_name' && !!execProblem} aria-describedby={f.hint ? `insp-${f.key}-hint` : undefined} />}
              {f.hint && <small className="insp-hint" id={`insp-${f.key}-hint`}>{f.hint}</small>}
              {f.key === 'executive_name' && execProblem && <small className="insp-hint warn" role="alert">{execProblem}</small>}
            </label>
          ))}

          {needsConsent && (
            <label className="insp-consent">
              <input type="checkbox" checked={consent} onChange={e => setConsent?.(e.target.checked)} required />
              <span>I have permission to run a check on this person’s profile.</span>
            </label>
          )}

          <p className="insp-note">Estimated collection cost: {spec.credits} Crustdata credits. Analysis uses up to 28 Gemini reviews on Vertex AI.</p>
          <button type="submit" className="insp-run" disabled={running || missing}>
            {running ? 'Collecting evidence…' : `Open a live ${spec.name} case`}
          </button>
        </form>}
        {section === 'trace' && <>
        <section className="insp-sec trace-toolbar"><h3>Investigation trace</h3>
          {caseOptions.length > 0 && (
            <label className="insp-f"><span>Filed investigation</span>
              <select disabled={running} value={record?.id || ''} onChange={e => onCase?.(e.target.value)}>
                <option value="">Select a recorded trace</option>
                {caseOptions.map(o => <option key={optId(o)} value={optId(o)}>{optName(o)}</option>)}
              </select>
            </label>
          )}
          {(running || record || events.length > 0) && <p>{record ? (replaying ? 'Recorded playback' : 'Recorded trace') : running ? 'Live investigation' : 'Interrupted investigation'} · {events.filter(e=>e.agent_id && e.event === 'end').length} of {agents.length} agent reports</p>}
          {(record?.swarm_events?.length > 0 || record?.collection_events?.length > 0) && <button type="button" className="trace-replay" onClick={onReplay}>{replaying ? 'Restart replay' : 'Replay handoffs'} ↻</button>}
        </section>
        {record && (
          <section className="insp-sec insp-result" aria-live="polite">
            <h3>Filed decision</h3>
            <div className="insp-verdict">{record.verdict}</div>
            {record.summary && <p>{record.summary}</p>}
            {record.council_decision && <p>Council · {record.council_decision.disposition}{record.council_decision.referred_by.length ? ' · ' + record.council_decision.referred_by.join(', ') : ''}</p>}
            {record.council_decision?.specialist_referrals?.length > 0 && <details className="insp-ev">
              <summary>Specialist referrals ({record.council_decision.specialist_referrals.length})</summary>
              {record.council_decision.specialist_referrals.map(id => <p key={id}>
                <button className="insp-parent" onClick={()=>onSelect(id)}>{reports[id]?.name || id} ↗</button>
              </p>)}
            </details>}
            {record.draft && <p className="insp-draft">{record.draft}</p>}
            {Array.isArray(record.evidence) && record.evidence.length > 0 && (
              <div className="insp-ev">
                <h4>Evidence</h4>
                {record.evidence.map((r, i) => (
                  <details key={i}><summary>{r.label}</summary><p>{r.detail}</p></details>
                ))}
              </div>
            )}
            <p className="insp-meta">
              {formatCredits(record.credits)}
              {record.receipt && <> · Receipt <code>{String(record.receipt).slice(0, 16)}</code></>}
            </p>
          </section>
        )}

        <section className="insp-sec">
          <h3>Recent activity</h3>
          {recent.length === 0
            ? <p className="insp-empty">No activity yet. Run the desk to see agents report.</p>
            : <ul className="insp-act">
                {recent.map((e, i) => (
                  <li key={i}>
                    <button type="button" onClick={() => e.agent_id && onSelect?.(e.agent_id)}>
                      <span className="insp-who">{e.name || e.agent_id || 'Collection'}<span className={`insp-st ${statusClass(e.status)}`}>{label(e.status)}</span></span>
                      {e.detail && <span className="insp-d">{e.detail}</span>}
                    </button>
                  </li>
                ))}
              </ul>}
        </section></>}
      </div>
      {section === 'agents' && <footer className="insp-footer"><button type="button" onClick={()=>setSection(running?'trace':'run')}>{running?'View investigation trace':'Configure investigation'} <span>↗</span></button></footer>}
    </aside>
  )
}
