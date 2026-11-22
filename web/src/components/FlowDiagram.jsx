import React from 'react'

/*
 * Intake → witnesses → review → verdicts for one desk. An input lights up as soon as
 * it has a value, and each witness lights up when any input feeding it is filled.
 */
const W = 760
const COL = { input: 6, source: 252, review: 520, verdict: 654 }
const NODE_W = { input: 184, source: 196, review: 100, verdict: 100 }

export default function FlowDiagram({ desk, values, mode }) {
  const live = mode === 'live'
  const filled = key => live && !!(values[key] || '').trim()
  const rowGap = 64
  const rows = Math.max(desk.fields.length, desk.sources.length)
  const H = Math.max(rows * rowGap, desk.verdicts.length * rowGap) + 28
  const fy = (i, n) => (H - n * rowGap) / 2 + i * rowGap + rowGap / 2
  const inputPos = Object.fromEntries(desk.fields.map((f, i) => [f.key, fy(i, desk.fields.length)]))
  const sourcePos = desk.sources.map((s, i) => fy(i, desk.sources.length))
  const mid = H / 2
  const curve = (x1, y1, x2, y2) => {
    const c = (x2 - x1) / 2
    return `M${x1} ${y1} C${x1 + c} ${y1}, ${x2 - c} ${y2}, ${x2} ${y2}`
  }
  const sourceLit = s => s.from.some(filled)
  const anyLit = desk.sources.some(sourceLit)

  return (
    <svg className="flow-diagram" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`How the ${desk.name} desk routes its inputs through witnesses to a verdict`} style={{ '--c': desk.color }}>
      {desk.sources.map((s, i) => s.from.filter(k => inputPos[k] != null).map(k => (
        <path key={s.id + k} d={curve(COL.input + NODE_W.input, inputPos[k], COL.source, sourcePos[i])}
          className={'edge' + (filled(k) ? ' lit' : '')} />
      )))}
      {sourcePos.map((y, i) => (
        <path key={'r' + i} d={curve(COL.source + NODE_W.source, y, COL.review, mid)} className={'edge' + (sourceLit(desk.sources[i]) ? ' lit' : '')} />
      ))}
      {desk.verdicts.map((v, i) => (
        <path key={v} d={curve(COL.review + NODE_W.review, mid, COL.verdict, fy(i, desk.verdicts.length))} className={'edge' + (anyLit ? ' lit' : '')} />
      ))}

      {desk.fields.map(f => (
        <g key={f.key} transform={`translate(${COL.input} ${inputPos[f.key] - 22})`} className={'node input' + (filled(f.key) ? ' lit' : '')}>
          <rect width={NODE_W.input} height="44" rx="3" />
          <text x="12" y="19" className="n-title">{f.label}</text>
          <text x="12" y="35" className="n-note">{f.key}</text>
        </g>
      ))}
      {desk.sources.map((s, i) => (
        <g key={s.id} transform={`translate(${COL.source} ${sourcePos[i] - 24})`} className={'node source' + (sourceLit(s) ? ' lit' : '')}>
          <rect width={NODE_W.source} height="48" rx="3" />
          <text x="12" y="21" className="n-title">{s.label}</text>
          <text x="12" y="37" className="n-note">{s.note}</text>
        </g>
      ))}
      <g transform={`translate(${COL.review} ${mid - 36})`} className="node review">
        <rect width={NODE_W.review} height="72" rx="3" />
        <text x="12" y="30" className="n-title">Opposing</text>
        <text x="12" y="46" className="n-title">counsel</text>
        <text x="12" y="62" className="n-note">then partner</text>
      </g>
      {desk.verdicts.map((v, i) => (
        <g key={v} transform={`translate(${COL.verdict} ${fy(i, desk.verdicts.length) - 20})`} className="node verdict">
          <rect width={NODE_W.verdict} height="40" rx="3" />
          <text x="10" y={v.length > 12 ? 17 : 24} className="n-verdict">{v.length > 12 ? 'REQUEST FOR' : v}</text>
          {v.length > 12 && <text x="10" y="30" className="n-verdict">EXPLANATION</text>}
        </g>
      ))}
    </svg>
  )
}
