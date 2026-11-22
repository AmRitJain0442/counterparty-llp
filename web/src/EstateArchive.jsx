import React, { useEffect, useState } from 'react'
import { formatCredits, formatDate, isLive, safeUrl } from './format'

/** Reopens estate cases that were filed live. Nothing is collected or spent by opening this page. */
export default function EstateArchive() {
  const [rows, setRows] = useState(null)
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    const abort = new AbortController()
    fetch('/api/cases', { signal: abort.signal }).then(r => {
      if (!r.ok) throw new Error()
      return r.json()
    }).then(all => {
      const estates = all.filter(c => c.desk === 'estate' && isLive(c))
        .sort((a, b) => String(b.created_at || b.as_of).localeCompare(String(a.created_at || a.as_of)))
      setRows(estates)
      setSelected(estates[0]?.id || '')
    }).catch(e => { if (e.name !== 'AbortError') setError('The ledger could not be opened.') })
    return () => abort.abort()
  }, [])
  const record = rows?.find(r => r.id === selected)
  return <section className="live-bench">
    <small>FILED ESTATES</small><h1>{record?.subject || 'Live estate cases'}</h1>
    {error ? <p role="alert">{error}</p> : !rows ? <p role="status">Reading the ledger…</p>
      : !rows.length ? <p>No live estate case is filed yet. Open one from the Live investigation room.</p> : <>
      <label>Filed estate<select value={selected} onChange={e => setSelected(e.target.value)}>
        {rows.map(r => <option key={r.id} value={r.id}>{r.subject || 'Untitled case'} · {formatDate(r.created_at || r.as_of)}</option>)}
      </select></label>
      {record && <>
        <p>LIVE · as of {formatDate(record.as_of, true)} · {formatCredits(record.credits)}</p>
        <h2>{record.verdict}</h2><p>{record.summary}</p>
        {record.flows?.length > 0 && <div className="bench-trace">{record.flows.map(flow => <div className="trace-line" key={flow.from + '>' + flow.to}>
          <span>{flow.from} → {flow.to}</span><b>{Number(flow.count) < 5 ? 'under 5' : flow.count} profiles</b>
        </div>)}</div>}
        {(record.evidence || []).map((e, i) => { const link = safeUrl(e.url); return <article key={i}>
          <h3>{String(e.label).replaceAll('_', ' ')}</h3><p>{e.detail}</p>
          {link && <a href={link} target="_blank" rel="noreferrer noopener">{e.source} ↗</a>}
        </article> })}
      </>}
    </>}
  </section>
}
