/** Thin client for the single-origin case API. */

async function request(path, options) {
  const response = await fetch(path, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = Array.isArray(body.detail)
      ? body.detail.map(d => d.msg).join(' ')
      : body.detail
    const error = new Error(typeof detail === 'string' && detail ? detail : 'The request could not be completed.')
    error.status = response.status
    throw error
  }
  return response.json()
}

export const listCases = signal => request('/api/cases', { signal })
export const getCase = (id, signal) => request('/api/cases/' + encodeURIComponent(id), { signal })
export const verifyReceipt = (id, signal) => request('/api/cases/' + encodeURIComponent(id) + '/receipt', { signal })

/** intake: {desk, mode, subject, consent, inputs} */
export const createCase = (intake, signal) => request('/api/cases', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(intake),
  signal,
})
