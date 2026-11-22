import React, { useRef, useState } from 'react'

/** A read-only price card for the shared firm's Crustdata account, read only on request. */
export default function AccountMeter() {
  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const controller = useRef(null)
  function load() {
    controller.current?.abort()
    controller.current = new AbortController()
    setLoading(true); setFailed(false)
    fetch('/api/capabilities', { signal: controller.current.signal })
      .then(response => {
        if (!response.ok) throw new Error('Unavailable')
        return response.json()
      })
      .then(setCard)
      .catch(error => { if (error.name !== 'AbortError') setFailed(true) })
      .finally(() => setLoading(false))
  }

  return <section aria-label="Provider entitlements" className="account-meter">
    <h2>Crustdata account</h2>
    {!card && <p>The price card reads the account’s endpoints and credit balance from Crustdata. It starts only when you ask.</p>}
    <button type="button" onClick={load} disabled={loading}>{loading ? 'Reading…' : card ? 'Refresh price card' : 'Read price card'}</button>
    {failed && <p role="status">Account price card unavailable.</p>}
    {card && <>
      <p>{card.credits == null ? 'Balance unavailable' : Number(card.credits).toLocaleString() + ' credits available'}
        {' · '}{card.status} · {new Date(card.as_of).toLocaleDateString()}</p>
      {!!card.endpoints.length && <div style={{overflowX:'auto'}}>
        <table><thead><tr><th>Endpoint</th><th>Access</th><th>Base credits</th><th>Requests/min</th></tr></thead>
        <tbody>{card.endpoints.map(row => <tr key={row.path}>
          <td><code>{row.path}</code></td><td>{row.status}</td>
          <td>{row.base_credits ?? '—'}</td><td>{row.effective_rate_limit_rpm ?? '—'}</td>
        </tr>)}</tbody></table>
      </div>}
    </>}
  </section>
}
