import React, { useEffect, useState } from 'react'
import './council.css'

const roles = [
  ['identity', 'Identity desk', 'Resolve the subject', '#8cb9df'],
  ['people', 'People desk', 'Date employment moves', '#b0c58c'],
  ['witness', 'Public witness', 'Read independent records', '#e2b368'],
  ['counsel', 'Opposing counsel', 'Test the proposed finding', '#fc8763'],
  ['partner', 'Partner review', 'File the decision', '#c6afe0'],
]
const positions = [[95,145],[270,77],[270,217],[456,146],[634,146]]
const edges = [[0,1],[0,2],[1,3],[2,3],[3,4]]

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
  return <section className="discussion-room">
    <div className="council-title"><div><small>INVESTIGATION WORKSPACE</small><h1>Discussion room</h1></div>
      {records.length > 0 && <label>Case file<select value={selected} onChange={e => setSelected(e.target.value)}>
        {records.map(row => <option key={row.id} value={row.id}>{row.subject} · {row.id.slice(0,6)}</option>)}
      </select></label>}</div>
    <p>Follow a filed case from identity resolution through independent review. Select a desk to inspect its evidence.</p>
    <div className="council-panel"><svg viewBox="0 0 720 302" role="group" aria-label="Select a desk on the evidence flow">
      <defs><pattern id="roomGrid" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#504c42"/></pattern></defs>
      <rect width="720" height="302" fill="url(#roomGrid)" />
      {edges.map(([a,b]) => {
        const [x,y]=positions[a], [u,v]=positions[b], mid=(x+u)/2
        return <path key={a+'-'+b} d={`M${x} ${y} C${mid} ${y}, ${mid} ${v}, ${u} ${v}`}
          fill="none" stroke={focus===a || focus===b ? roles[b][3] : '#5b574b'} strokeWidth="1.7"/>
      })}
      {roles.map(([key,name,,color],i) => {
        const [x,y]=positions[i], active=i===focus
        return <g key={key} transform={`translate(${x},${y})`} tabIndex="0" role="button" aria-label={name}
          aria-pressed={active} onClick={() => setFocus(i)} onKeyDown={e => {
            if(['Enter',' '].includes(e.key)){e.preventDefault();setFocus(i)}
          }}><circle r="28" fill="#171610" stroke={color} strokeWidth={active ? 2.7 : 1}/>
          <path d="m0 -12 11 6 v12 l-11 6 -11 -6 v-12z" stroke={color} fill={active?color:'none'}/>
          <text y="48" textAnchor="middle" fill={active?'#fff1da':'#bcb5a2'}>{name}</text>
        </g>
      })}
    </svg></div>
    <section className="council-notes" aria-live="polite"><div><small style={{color:roles[focus][3]}}>{roles[focus][1]}</small>
      <h2>{roles[focus][2]}</h2>{record && <p>{record.subject} · {record.mode.toUpperCase()}</p>}</div>
      <div>{error || (!record ? 'Run a desk investigation to see its evidence here.' :
        evidence.length ? evidence.map((e,i) => <article key={i}><strong>{e.label}</strong><p>{e.detail}</p></article>) :
          'This case has no filed observation from this desk.')}</div>
    </section>
  </section>
}
