import React, { useEffect, useState } from 'react'
import HumanReview from './HumanReview'
import { modeLabel } from './format'
import './council.css'

const roles = [
  ['identity', 'Identity desk', 'Resolve the subject', '#8cb9df'],
  ['people', 'People desk', 'Date employment moves', '#b0c58c'],
  ['witness', 'Public witness', 'Read independent records', '#e2b368'],
  ['counsel', 'Opposing counsel', 'Test the proposed finding', '#fc8763'],
  ['partner', 'Partner review', 'File the decision', '#c6afe0'],
]
function FiledReport({report, evidence, children}) {
  const cards = (report.refs || []).map(id => evidence.get(id)).filter(Boolean)
  return <details className="filed-report">
    <summary>{report.name} <small>{report.status}</small></summary>
    {report.persona && <p className="report-persona">{report.persona}</p>}
    <p>{report.detail}</p>
    {report.assessment === 'needs_evidence' && <p className="report-referral">Further evidence requested</p>}
    {cards.length > 0 && <details className="report-citations"><summary>Source cards ({cards.length})</summary>
      <ul>{cards.map(card => <li key={card.id}>{card.label} <small>{card.source}</small></li>)}</ul>
    </details>}
    {children}
  </details>
}

function observations(record, role) {
  const items = record?.evidence || []
  if (role === 'counsel') return [
    ...(record?.reviews?.counsel ? [{label:record.reviews.counsel.name,detail:record.reviews.counsel.detail}] : []),
    {label:'Rule-based finding',detail:record?.summary}
  ]
  if (role === 'partner') return [{label:record?.verdict,detail:record?.draft || record?.summary}]
  if (role === 'identity') return items.filter(e => /identit|identify|matched company|resolution/i.test(e.label))
  if (role === 'people') return items.filter(e => /crustdata|employment|headcount|profile|workforce/i.test(e.source + ' ' + e.label))
  return items.filter(e => !/crustdata|gemini|internal|partner|counsel/i.test(e.source))
}

export default function DiscussionRoom({initialCase}) {
  const [records, setRecords] = useState(initialCase ? [initialCase] : [])
  const [selected, setSelected] = useState(initialCase?.id || '')
  const [focus, setFocus] = useState(0)
  const [error, setError] = useState('')
  useEffect(() => {
    const c = new AbortController()
    fetch('/api/cases', {signal:c.signal}).then(r => {
      if (!r.ok) throw new Error()
      return r.json()
    }).then(rows => {
      setRecords(rows)
      setSelected(current => rows.some(r => r.id === current) ? current : rows[0]?.id || '')
    }).catch(e => { if(e.name !== 'AbortError') setError('The ledger could not be opened.') })
    return () => c.abort()
  }, [])
  const record = records.find(row => row.id === selected)
  const evidence = record ? observations(record, roles[focus][0]) : []
  const reports = record?.swarm_reports || []
  const leads = reports.filter(report => !report.parent_id)
  const cards = new Map((record?.evidence || []).map(card => [card.id, card]))
  return <section className="discussion-room">
    <div className="council-title"><div><small>INVESTIGATION WORKSPACE</small><h1>Discussion room</h1></div>
      {records.length > 0 && <label>Case file<select value={selected} onChange={e => setSelected(e.target.value)}>
        {records.map(row => <option key={row.id} value={row.id}>{row.subject} · {row.id.slice(0,6)}</option>)}
      </select></label>}</div>
    {record?.swarm_reports?.length > 0 && <section className="room-trace">
      <a href={'/?case='+encodeURIComponent(record.id)+'#swarm'}>Open this case in the swarm inspector ↗</a>
      <p>{reports.length > leads.length ? `${leads.length} leads · ${reports.length - leads.length} specialists` : `${leads.length} agent reports`}</p>
      <div>{['identity','discovery','challenge','decision'].map(group=><section key={group}>
        <h2>{group}</h2>
        {leads.filter(lead => lead.group === group).map(lead => {
          const team = reports.filter(report => report.parent_id === lead.agent_id)
          return <FiledReport key={lead.agent_id} report={lead} evidence={cards}>
            {team.length > 0 && <div className="filed-team"><h3>Specialist reports</h3>
              {team.map(report => <FiledReport key={report.agent_id} report={report} evidence={cards}/>)}
            </div>}
          </FiledReport>
        })}
      </section>)}</div></section>}
    {record && !record.swarm_reports?.length && <p>This case predates agent tracing. Its filed evidence is available below.</p>}
    <div className="room-evidence-nav" aria-label="Filed evidence by role">
      {roles.map(([id,name],i)=><button key={id} aria-pressed={focus===i} onClick={()=>setFocus(i)}>{name}</button>)}
    </div>
    <section className="council-notes" aria-live="polite"><div><small style={{color:roles[focus][3]}}>{roles[focus][1]}</small>
      <h2>{roles[focus][2]}</h2>{record && <p>{record.subject} · {modeLabel(record.mode).toUpperCase()}</p>}</div>
      <div>{error || (!record ? 'Open a live investigation to see its evidence here.' :
        evidence.length ? evidence.map((e,i) => <article key={i}><strong>{e.label}</strong><p>{e.detail}</p></article>) :
          'This case has no filed observation from this desk.')}</div>
    </section>
    {record && <HumanReview key={record.id} caseId={record.id}/>}
  </section>
}
