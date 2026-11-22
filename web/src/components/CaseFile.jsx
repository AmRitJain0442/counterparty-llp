import React, { useEffect, useState } from 'react'
import { DESK_BY_ID } from '../desks'
import { verifyReceipt } from '../api'
import { evidenceBadge, formatCredits, formatDate, safeUrl, shortDigest, statusTone, verdictTone } from '../format'
import Sankey from './Sankey'
import './case.css'

const FLOW_TITLE = {
  estate: ['Where the staff went', 'people'],
  payment: ['How the evidence moved', 'signals'],
  candidate: ['How the evidence moved', 'signals'],
  company: ['How the evidence moved', 'signals'],
}

function Evidence({ rows }) {
  if (!rows?.length) return <p className="none">This case filed no evidence rows.</p>
  return (
    <ol className="evidence">
      {rows.map((row, i) => {
        const link = safeUrl(row.url)
        const badge = evidenceBadge(row)
        return (
          <li key={i}>
            <details>
              <summary>
                <span className="e-label">{row.label}</span>
                <span className="e-source">{row.source}</span>
                <span className={'pill ' + (badge === 'LIVE' ? 'tone-clear' : badge === 'DEMO' || badge === 'CACHED' || badge === 'REPLAY' ? 'tone-sign' : 'tone-neutral')}>{badge}</span>
              </summary>
              <div className="e-body">
                <p>{row.detail}</p>
                <dl>
                  <div><dt>As of</dt><dd>{formatDate(row.as_of)}</dd></div>
                  <div><dt>Source</dt><dd>{row.source}</dd></div>
                  {link && <div><dt>Record</dt><dd><a href={link} target="_blank" rel="noreferrer noopener">Open the source ↗</a></dd></div>}
                </dl>
              </div>
            </details>
          </li>
        )
      })}
    </ol>
  )
}

function Receipt({ record }) {
  const [copied, setCopied] = useState(false)
  const [check, setCheck] = useState(null)
  useEffect(() => { setCopied(false); setCheck(null) }, [record.id])

  async function copy() {
    try { await navigator.clipboard.writeText(record.receipt); setCopied(true); setTimeout(() => setCopied(false), 1600) } catch { setCopied(false) }
  }
  async function verify() {
    setCheck({ state: 'running' })
    try {
      const result = await verifyReceipt(record.id)
      setCheck({ state: 'done', status: String(result.status) })
    } catch (e) {
      setCheck({ state: 'error', message: e.message })
    }
  }
  return (
    <div className="receipt">
      <span className="label">Evidence receipt</span>
      <code title={record.receipt}>{shortDigest(record.receipt || '')}</code>
      <div className="receipt-actions">
        <button type="button" className="btn small" onClick={copy}>{copied ? 'Copied' : 'Copy digest'}</button>
        <button type="button" className="btn small" onClick={verify} disabled={check?.state === 'running'}>Verify receipt</button>
      </div>
      <p aria-live="polite" className={'receipt-check ' + (check?.state === 'error' ? 'tone-hold' : check?.state === 'done' ? 'tone-clear' : '')}>
        {check?.state === 'running' && 'Checking the ledger…'}
        {check?.state === 'done' && `Ledger says: ${check.status}.`}
        {check?.state === 'error' && check.message}
      </p>
    </div>
  )
}

export default function CaseFile({ record, loading, error }) {
  if (loading) return <div className="case-file empty" role="status">Opening the case file…</div>
  if (error) return <div className="case-file empty" role="alert">{error}</div>
  if (!record) {
    return (
      <div className="case-file empty">
        <span className="label">Case file</span>
        <p>Run a desk above or pick a row in the ledger. The verdict, steps, every piece of evidence and the receipt appear here.</p>
      </div>
    )
  }
  const desk = DESK_BY_ID[record.desk]
  const tone = verdictTone(record.verdict)
  const evidence = record.evidence || []
  const crust = evidence.filter(e => /crustdata/i.test(e.source)).length
  const witnessOutside = evidence.filter(e => !/crustdata|gemini|internal/i.test(e.source)).length
  const [flowTitle, unit] = FLOW_TITLE[record.desk] || FLOW_TITLE.payment

  return (
    <article className="case-file" id="case-file" style={{ '--c': desk?.color || 'var(--hot)' }} aria-labelledby="case-verdict">
      <header className="case-head">
        <div className="verdict-block">
          <span className="label">{desk ? `${desk.name} desk · ${desk.alias}` : record.desk}</span>
          <h3 id="case-verdict" className={'verdict tone-' + tone}>{record.verdict}</h3>
        </div>
        <div className="case-meta">
          <h4>{record.subject || 'Seeded demonstration case'}</h4>
          <div className="chips">
            <span className={'pill ' + (record.mode === 'live' ? 'tone-clear' : 'tone-sign')}>{record.mode}</span>
            <span className="chip">As of {formatDate(record.as_of, true)}</span>
            <span className="chip">{formatCredits(record.credits)}</span>
          </div>
        </div>
      </header>

      <p className="case-summary">{record.summary}</p>
      {record.draft && (
        <div className="draft"><span className="label">Drafting counsel’s note</span><p>{record.draft}</p></div>
      )}

      <div className="case-grid">
        <section aria-labelledby="steps-h">
          <h4 id="steps-h" className="label">Steps taken</h4>
          {record.steps?.length ? (
            <ol className="steps">
              {record.steps.map((s, i) => (
                <li key={i} className={'tone-' + statusTone(s.status)}>
                  <div><b>{s.name}</b><span className="pill">{s.status}</span></div>
                  {s.detail && <p>{s.detail}</p>}
                </li>
              ))}
            </ol>
          ) : <p className="none">No steps recorded.</p>}
        </section>

        <section aria-labelledby="ev-h">
          <h4 id="ev-h" className="label">Evidence · {evidence.length} rows</h4>
          <p className="witness-line">
            <span>{crust} from Crustdata</span><span>{witnessOutside} from independent public sources</span>
            <span className={crust && witnessOutside ? 'tone-clear' : 'tone-hold'}>{crust && witnessOutside ? 'Two witnesses present' : 'Fewer than two witnesses'}</span>
          </p>
          <Evidence rows={evidence} />
        </section>
      </div>

      {!!record.flows?.length && (
        <section className="case-flows" aria-labelledby="fl-h">
          <h4 id="fl-h" className="label">{flowTitle}</h4>
          <Sankey flows={record.flows} color={desk?.color} unit={unit} maskSmall={record.desk === 'estate'}
            label={`${flowTitle} for ${record.subject || 'this case'}`} />
        </section>
      )}

      <Receipt record={record} />
    </article>
  )
}
