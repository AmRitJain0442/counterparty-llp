import React, { useEffect, useState } from 'react'
import AccountMeter from './AccountMeter'

export default function ProviderRoom() {
  const [watch, setWatch] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/watch', { signal: controller.signal }).then(r => {
      if (!r.ok) throw new Error()
      return r.json()
    }).then(setWatch).catch(error => { if (error.name !== 'AbortError') setFailed(true) })
    return () => controller.abort()
  }, [])
  return <div className="provider-room">
    <section aria-label="Watch history">
      <h2>Company watch</h2>
      {watch ? <>
        <p>{watch.domains?.join(', ') || 'Company watch'} · {watch.status}
          {watch.refresh_days ? ' · ' + watch.refresh_days + '-day refresh' : ''}</p>
        {watch.runs.length > 0 ? <table><thead><tr><th>Run date</th><th>State</th><th>Records checked</th><th>Credits</th></tr></thead>
          <tbody>{watch.runs.map(run => <tr key={run.id}><td>{new Date(run.started_at).toLocaleString()}</td>
            <td>{run.status}</td><td>{run.records_searched ?? '—'}</td><td>{run.credits_deducted ?? '—'}</td></tr>)}</tbody>
        </table> : <p>No run history available.</p>}
        {watch.expires_at && <p>Watch expires {watch.expires_at}.</p>}
      </> : <p role="status">{failed ? 'Watch history unavailable.' : 'Reading watch history…'}</p>}
    </section>
    <AccountMeter />
  </div>
}
