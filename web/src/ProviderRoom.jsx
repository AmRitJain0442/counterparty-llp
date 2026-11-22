import React, { useRef, useState } from 'react'
import AccountMeter from './AccountMeter'

/** Provider lookups run only when the reader asks for them, never on page load. */
export default function ProviderRoom() {
  const [watch, setWatch] = useState(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const controller = useRef(null)
  function load() {
    controller.current?.abort()
    controller.current = new AbortController()
    setLoading(true); setFailed(false)
    fetch('/api/watch', { signal: controller.current.signal }).then(r => {
      if (!r.ok) throw new Error()
      return r.json()
    }).then(setWatch).catch(error => { if (error.name !== 'AbortError') setFailed(true) })
      .finally(() => setLoading(false))
  }
  return <div className="provider-room">
    <section aria-label="Watch history">
      <h2>Company watch</h2>
      {!watch && <p>Reading the history makes a request to the provider’s watch endpoint. It starts only when you ask.</p>}
      <button type="button" onClick={load} disabled={loading}>{loading ? 'Reading…' : watch ? 'Refresh watch history' : 'Read watch history'}</button>
      {failed && <p role="status">Watch history unavailable.</p>}
      {watch && <>
        <p>{watch.domains?.join(', ') || 'Company watch'} · {watch.status}
          {watch.refresh_days ? ' · ' + watch.refresh_days + '-day refresh' : ''} · as of {new Date(watch.as_of).toLocaleString()}</p>
        {watch.runs.length > 0 ? <table><thead><tr><th>Run date</th><th>State</th><th>Records checked</th><th>Credits</th></tr></thead>
          <tbody>{watch.runs.map(run => <tr key={run.id}><td>{new Date(run.started_at).toLocaleString()}</td>
            <td>{run.status}</td><td>{run.records_searched ?? '—'}</td><td>{run.credits_deducted ?? '—'}</td></tr>)}</tbody>
        </table> : <p>No run history available.</p>}
        {watch.expires_at && <p>Watch expires {watch.expires_at}.</p>}
      </>}
    </section>
    <AccountMeter />
  </div>
}
