/** Consume provider events even when a JSON line spans multiple HTTP chunks. */
export async function streamCase(intake, onStep, signal) {
  const response = await fetch('/api/cases/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(intake),
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Check the investigation inputs.')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  let filed
  function consume(line) {
    if (!line.trim()) return
    const event = JSON.parse(line)
    if (event.type === 'error') throw new Error(event.detail)
    if (event.type === 'step') onStep(event)
    if (event.type === 'case') filed = event.case
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      pending += decoder.decode(value, { stream: !done })
      const lines = pending.split('\n')
      pending = lines.pop()
      lines.forEach(consume)
      if (done) break
    }
    consume(pending)
  } finally {
    reader.releaseLock()
  }
  if (!filed) throw new Error('The connection closed before a ledger receipt arrived. Check the ledger before retrying.')
  return filed
}
