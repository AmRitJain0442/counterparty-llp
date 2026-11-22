import React, { useMemo, useState } from 'react'
import { DESKS, DESK_BY_ID } from '../desks'
import { formatCredits, formatDate, shortDigest, verdictTone } from '../format'
import './ledger.css'

export default function Ledger({ cases, loading, error, selectedId, onSelect, onRetry }) {
  const [desk, setDesk] = useState('all')
  const [mode, setMode] = useState('all')

  const rows = useMemo(() => [...cases]
    .sort((a, b) => String(b.created_at || b.as_of).localeCompare(String(a.created_at || a.as_of)))
    .filter(c => (desk === 'all' || c.desk === desk) && (mode === 'all' || c.mode === mode)), [cases, desk, mode])
  const metered = cases.filter(c => c.credits != null)
  const total = metered.reduce((s, c) => s + Number(c.credits), 0)

  return (
    <div className="ledger">
      <div className="ledger-top">
        <dl className="tally">
          <div><dt>Cases filed</dt><dd>{cases.length}</dd></div>
          <div><dt>Credits metered</dt><dd>{metered.length ? total.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}</dd></div>
          {DESKS.map(d => (
            <div key={d.id} style={{ '--c': d.color }}><dt>{d.name}</dt><dd>{cases.filter(c => c.desk === d.id).length}</dd></div>
          ))}
        </dl>
        <div className="filters">
          <label>Desk
            <select id="ledger-desk" value={desk} onChange={e => setDesk(e.target.value)}>
              <option value="all">All desks</option>
              {DESKS.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <label>Mode
            <select id="ledger-mode" value={mode} onChange={e => setMode(e.target.value)}>
              <option value="all">Demo and live</option>
              <option value="demo">Demo</option>
              <option value="live">Live</option>
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <div className="ledger-empty" role="alert">
          <p>{error}</p>
          <button type="button" className="btn small" onClick={onRetry}>Try again</button>
        </div>
      ) : loading && !cases.length ? (
        <div className="ledger-empty" role="status">Reading the ledger…</div>
      ) : !rows.length ? (
        <div className="ledger-empty">
          <p>{cases.length ? 'No case matches these filters.' : 'The ledger is empty. Run a desk above and its case will be filed here with a receipt.'}</p>
        </div>
      ) : (
        <div className="ledger-scroll">
          <table>
            <thead>
              <tr><th>Filed</th><th>Desk</th><th>Subject</th><th>Mode</th><th>Verdict</th><th className="num">Credits</th><th>Receipt</th></tr>
            </thead>
            <tbody>
              {rows.map(c => {
                const d = DESK_BY_ID[c.desk]
                return (
                  <tr key={c.id} className={c.id === selectedId ? 'selected' : ''} style={{ '--c': d?.color }}>
                    <td className="mono">{formatDate(c.created_at || c.as_of)}</td>
                    <td><span className="desk-tag">{d?.name || c.desk}</span></td>
                    <td className="subject">
                      <button type="button" onClick={() => onSelect(c.id)} aria-current={c.id === selectedId ? 'true' : undefined}>
                        {c.subject || 'Seeded demonstration case'}
                      </button>
                    </td>
                    <td><span className={'pill ' + (c.mode === 'live' ? 'tone-clear' : 'tone-sign')}>{c.mode}</span></td>
                    <td><b className={'tone-' + verdictTone(c.verdict)}>{c.verdict}</b></td>
                    <td className="num mono">{formatCredits(c.credits)}</td>
                    <td className="mono dim">{shortDigest(c.receipt || '')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
