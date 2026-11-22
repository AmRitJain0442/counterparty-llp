import { useEffect, useMemo, useRef, useState } from 'react'
import { DESKS, DESK_BY_ID } from '../desks'
import { formatCredits } from '../format'
import './inspector.css'

const GROUPS = [
  ['identity', 'Identity', 'Resolve who or what the subject is'],
  ['discovery', 'Discovery', 'Collect dated witnesses'],
  ['challenge', 'Challenge', 'Test competing explanations'],
  ['decision', 'Decision', 'Reconcile findings and file the case'],
]
const STATUS_LABEL = { idle: 'Idle', queued: 'Queued', running: 'Running', done: 'Done', complete: 'Done', ok: 'Done', error: 'Failed', failed: 'Failed', blocked: 'Blocked', held: 'Held' }

const norm = s => String(s || 'idle').toLowerCase()
const statusClass = s => {
  const n = norm(s)
  if (n === 'running') return 'run'
  if (['done', 'complete', 'ok'].includes(n)) return 'ok'
  if (['error', 'failed', 'blocked'].includes(n)) return 'bad'
  return 'idle'
}
const label = s => STATUS_LABEL[norm(s)] || String(s)
const optId = o => (typeof o === 'string' ? o : o.id ?? o.value ?? o.key)
const optName = o => (typeof o === 'string' ? o : o.label ?? o.name ?? o.title ?? String(optId(o)))

export default function Inspector({
  desk, agent, agents = [], events = [], onSelect, onClose, onRun, running, record, mode = 'demo', setMode,
  subject = '', setSubject, inputs = {}, setInputs, consent = false, setConsent, onDesk, caseOptions = [], onCase, error,
  section, setSection, onReplay, replaying, runMode,
}) {
  const spec = DESK_BY_ID[desk] || DESKS[0]
  const [open, setOpen] = useState({})
  const [caseId, setCaseId] = useState('')
  const body = useRef(null)
  useEffect(() => { body.current?.scrollTo(0, 0) }, [section, agent?.id, desk])
  const live = mode === 'live'

  const latest = useMemo(() => {
    const m = {}
    for (const e of events) m[e.agent_id] = e
    return m
  }, [events])
  const byGroup = useMemo(() => {
    const m = {}
    for (const [g] of GROUPS) m[g] = agents.filter(a => a.group === g)
    return m
  }, [agents])

  const upstream = agents.filter(a => agent?.depends_on?.includes(a.id))
  const downstream = agents.filter(a => a.depends_on?.includes(agent?.id))
  const ev = agent ? latest[agent.id] : null
  const report = record?.swarm_reports?.find(r => r.agent_id === agent?.id)
  const recent = events.slice(-8).reverse()
  const needsConsent = live && (spec.alwaysConsent || spec.consentFor?.some(k => (inputs[k] || '').trim()))
  const rosterOpen = g => open[g] ?? (agent ? agent.group === g : g === 'identity')
  const missing = live && (!subject.trim() || spec.fields.some(f => f.required && !(inputs[f.key] || '').trim()) || (needsConsent && !consent))

  const submit = e => { e.preventDefault(); if (!running && !missing) onRun?.() }

  return (
    <aside className="insp" style={{ '--desk': spec.color }} aria-label="Agent inspector">
      <header className="insp-head">
        <div className="insp-title"><span>{section === 'agents' && agent ? agent.group + ' swarm' : 'Investigation desk'}</span>
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
          <h3>Assignment</h3><p>{agent.task.replace(/^.*?: /,'')}</p>
          <dl className="insp-facts">
            <div><dt>Receives from</dt><dd>{upstream.map(a=>a.name).join(', ') || 'Case evidence'}</dd></div>
            <div><dt>Hands off to</dt><dd>{downstream.map(a=>a.name).join(', ') || 'Case ledger'}</dd></div>
            <div><dt>Status</dt><dd>{label(ev?.status)}</dd></div>
          </dl>
          {report && <details className="agent-report"><summary>Read agent report</summary><p>{report.detail}</p>
            {report.assessment && <p>Assessment · {report.assessment.replaceAll('_',' ')}</p>}
            {report.refs.map(id => {
              const row = record.evidence.find(e=>e.id===id)
              return row && <details key={id}><summary>{row.label} · {row.source}</summary><p>{row.detail}</p><small>{row.as_of}</small></details>
            })}</details>}
        </section>}
        <section className="insp-sec">
          <h3>Swarm roster <span>{agents.length} agents</span></h3>
          {GROUPS.map(([g, name, hint]) => (
            <div key={g} className="insp-acc">
              <button type="button" aria-expanded={rosterOpen(g)} onClick={() => setOpen({ ...open, [g]: !rosterOpen(g) })}>
                <span>{name}<small>{hint}</small></span><em>{byGroup[g].length} agents</em>
              </button>
              {rosterOpen(g) && (
                <ul>
                  {byGroup[g].length === 0 && <li className="insp-empty">No agents in this group</li>}
                  {byGroup[g].map(a => (
                    <li key={a.id}>
                      <button type="button" className={agent?.id === a.id ? 'on' : ''} aria-pressed={agent?.id === a.id} onClick={() => onSelect?.(a.id)}>
                        <span>{a.name}</span><span className={`insp-st ${statusClass(latest[a.id]?.status)}`}>{label(latest[a.id]?.status)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </section>

        </>}
        {section === 'run' && <form className="insp-sec insp-form" onSubmit={submit}>
          <h3>Investigation mode</h3>
          <div className="insp-mode" role="radiogroup" aria-label="Run mode">
            {['demo', 'live'].map(m => (
              <label key={m} className={mode === m ? 'on' : ''}>
                <input type="radio" name="insp-mode" checked={mode === m} onChange={() => setMode?.(m)} />{m === 'demo' ? 'Demo' : 'Live'}
              </label>
            ))}
          </div>

          <label className="insp-f"><span>{live ? 'Subject' : 'Subject (optional)'}</span>
            <input value={subject} maxLength={180} required={live} onChange={e => setSubject?.(e.target.value)}
              placeholder={live ? 'The company or person being checked' : 'Leave blank to use the seeded case'} />
          </label>

          {live && spec.fields.map(f => (
            <label key={f.key} className="insp-f"><span>{f.label}{f.required ? '' : ' (optional)'}</span>
              {f.long
                ? <textarea rows={3} value={inputs[f.key] || ''} required={f.required} placeholder={f.placeholder} onChange={e => setInputs?.({ ...inputs, [f.key]: e.target.value })} />
                : <input value={inputs[f.key] || ''} required={f.required} placeholder={f.placeholder} onChange={e => setInputs?.({ ...inputs, [f.key]: e.target.value })} />}
            </label>
          ))}

          {needsConsent && (
            <label className="insp-consent">
              <input type="checkbox" checked={consent} onChange={e => setConsent?.(e.target.checked)} required />
              <span>I have permission to run a check on this person’s profile.</span>
            </label>
          )}

          {live && <p className="insp-note">Live runs spend about {spec.credits} credits. Demo runs spend none.</p>}
          <button type="submit" className="insp-run" disabled={running || missing}>
            {running ? 'Collecting evidence…' : live ? `Open a live ${spec.name} case` : `Run the ${spec.name} demo`}
          </button>
        </form>}
        {section === 'trace' && <>
        <section className="insp-sec trace-toolbar"><h3>Investigation trace</h3>
          {caseOptions.length > 0 && (
            <label className="insp-f"><span>Filed investigation</span>
              <select disabled={running} value={caseId} onChange={e => { setCaseId(e.target.value); onCase?.(e.target.value) }}>
                <option value="">Select a recorded trace</option>
                {caseOptions.map(o => <option key={optId(o)} value={optId(o)}>{optName(o)}</option>)}
              </select>
            </label>
          )}
          {events.length > 0 && <p>{runMode === 'demo' ? 'Synthetic investigation' : 'Live investigation'} · {events.filter(e=>e.agent_id && e.event === 'end').length} of {agents.length} agent reports</p>}
          {record && <button type="button" className="trace-replay" onClick={onReplay}>{replaying ? 'Restart replay' : 'Replay handoffs'} ↻</button>}
        </section>
        {record && (
          <section className="insp-sec insp-result" aria-live="polite">
            <h3>Filed decision</h3>
            <div className="insp-verdict">{record.verdict}</div>
            {record.summary && <p>{record.summary}</p>}
            {record.council_decision && <p>Council · {record.council_decision.disposition}{record.council_decision.referred_by.length ? ' · ' + record.council_decision.referred_by.join(', ') : ''}</p>}
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
