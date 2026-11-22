import React, { useEffect, useState } from 'react'

/** A read-only price card for the shared firm's Crustdata account. */
export default function AccountMeter() {
  const [card, setCard] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/capabilities', { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Unavailable')
        return response.json()
      })
      .then(setCard)
      .catch(error => { if (error.name !== 'AbortError') setFailed(true) })
    return () => controller.abort()
  }, [])

  return <section aria-label="Provider entitlements" className="account-meter">
    <h2>Crustdata account</h2>
    {!card && <p role="status">{failed ? 'Account price card unavailable.' : 'Reading the account price card…'}</p>}
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
