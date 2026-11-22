/** Display helpers shared by the ledger, case file and Sankey. */

/** hold: needs a human call-back. clear: nothing adverse. kill: the finding was withdrawn. sign: a forward prediction. */
export function verdictTone(verdict = '') {
  const v = String(verdict).toUpperCase()
  if (/RELEASED|VERIFIED|CLEAR/.test(v)) return 'clear'
  if (/KILLED|WITHDRAWN/.test(v)) return 'kill'
  if (/SIGNED/.test(v)) return 'sign'
  if (/HELD|FAILED|REQUEST|EXPLANATION|INSUFFICIENT/.test(v)) return 'hold'
  return 'neutral'
}

export function formatDate(value, withTime = false) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const day = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
  if (!withTime) return day
  return day + ' Â· ' + date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

export function formatCredits(credits) {
  if (credits == null || Number.isNaN(Number(credits))) return 'Not metered'
  const n = Number(credits)
  return (Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 })) + ' cr'
}

export function shortDigest(digest = '') {
  return digest.length > 18 ? digest.slice(0, 10) + 'â€¦' + digest.slice(-6) : digest
}

export function safeUrl(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null
}

/** Evidence from replayed or cached data carries its own label so it is never read as live. */
export function evidenceBadge(row) {
  const text = String(row.mode || '').toUpperCase()
  return ['LIVE', 'CACHED', 'REPLAY'].includes(text) ? text : 'UNVERIFIED'
}

/** Cases filed before the desks went live-only are labelled as stored replays, never as live. */
export function modeLabel(mode) {
  return String(mode).toLowerCase() === 'live' ? 'Live' : 'Stored replay'
}

export const isLive = record => String(record?.mode).toLowerCase() === 'live'

export function statusTone(status = '') {
  const s = String(status).toLowerCase()
  if (/ok|done|complete|success|filed|pass/.test(s)) return 'clear'
  if (/run|pending|wait|progress/.test(s)) return 'sign'
  if (/skip|unavailable|none|empty/.test(s)) return 'neutral'
  if (/fail|error|denied|blocked/.test(s)) return 'hold'
  return 'neutral'
}
