import React, { useMemo, useState } from 'react'
import './sankey.css'

const W = 940, PAD_Y = 12, NODE_W = 14, GAP = 12, LABEL_W = 190

/** Longest-path layering with a bound so a cyclic feed cannot hang the render. */
function layout(flows, height) {
  const clean = flows.filter(f => f.from && f.to && f.from !== f.to && Number(f.count) > 0)
    .map(f => ({ from: String(f.from), to: String(f.to), count: Number(f.count) }))
  const names = [...new Set(clean.flatMap(f => [f.from, f.to]))]
  if (!names.length) return null
  const layer = Object.fromEntries(names.map(n => [n, 0]))
  for (let pass = 0; pass < names.length; pass++) {
    let moved = false
    for (const f of clean) {
      if (layer[f.to] < layer[f.from] + 1 && layer[f.from] < names.length) { layer[f.to] = layer[f.from] + 1; moved = true }
    }
    if (!moved) break
  }
  const depth = Math.max(...Object.values(layer)) + 1
  const nodes = names.map(name => {
    const out = clean.filter(f => f.from === name).reduce((s, f) => s + f.count, 0)
    const inn = clean.filter(f => f.to === name).reduce((s, f) => s + f.count, 0)
    return { name, layer: layer[name], value: Math.max(out, inn), out, inn }
  })
  const columns = Array.from({ length: depth }, (_, i) => nodes.filter(n => n.layer === i).sort((a, b) => b.value - a.value))
  const ky = Math.min(...columns.map(col => (height - 2 * PAD_Y - GAP * (col.length - 1)) / col.reduce((s, n) => s + n.value, 0)))
  const colX = i => depth === 1 ? 0 : i * ((W - LABEL_W - NODE_W) / (depth - 1))
  const byName = Object.fromEntries(nodes.map(n => [n.name, n]))

  // Two barycentre passes to untangle crossings, then stack each column centred vertically.
  const place = () => columns.forEach(col => {
    const total = col.reduce((s, n) => s + n.value * ky, 0) + GAP * (col.length - 1)
    let y = (height - total) / 2
    col.forEach(n => { n.y = y; n.h = Math.max(n.value * ky, 3); y += n.h + GAP })
  })
  place()
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 1; i < depth; i++) {
      columns[i].forEach(n => {
        const ins = clean.filter(f => f.to === n.name)
        const w = ins.reduce((s, f) => s + f.count, 0)
        n.bary = w ? ins.reduce((s, f) => s + (byName[f.from].y + byName[f.from].h / 2) * f.count, 0) / w : n.y
      })
      columns[i].sort((a, b) => a.bary - b.bary)
    }
    place()
  }

  const outCursor = {}, inCursor = {}
  nodes.forEach(n => { outCursor[n.name] = n.y; inCursor[n.name] = n.y })
  const links = clean
    .map((f, index) => ({ ...f, index, a: byName[f.from], b: byName[f.to] }))
    .sort((p, q) => p.b.y - q.b.y || p.a.y - q.a.y)
  links.forEach(l => { l.t = Math.max(l.count * ky, 2) })
  const outs = [...links].sort((p, q) => p.b.y - q.b.y)
  outs.forEach(l => { l.y0 = outCursor[l.from] + l.t / 2; outCursor[l.from] += l.t })
  const ins = [...links].sort((p, q) => p.a.y - q.a.y)
  ins.forEach(l => { l.y1 = inCursor[l.to] + l.t / 2; inCursor[l.to] += l.t })
  nodes.forEach(n => { n.x = colX(n.layer) })
  return { nodes, links, depth }
}

const clip = (s, n = 28) => s.length > n ? s.slice(0, n - 1) + '…' : s

export default function Sankey({ flows, color = '#e3b96e', maskSmall = false, unit = 'people', label }) {
  const [hover, setHover] = useState(null)
  const height = Math.max(320, Math.min(520, 70 + new Set((flows || []).map(f => f.to)).size * 34))
  const graph = useMemo(() => layout(flows || [], height), [flows, height])
  if (!graph) return <p className="sankey-empty">This case recorded no movement between groups.</p>
  const show = n => maskSmall && n < 5 ? 'fewer than 5' : n.toLocaleString()
  const active = hover == null ? null : graph.links[hover]
  const touches = (l, node) => l.from === node || l.to === node
  const caption = active
    ? `${active.from} to ${active.to}: ${show(active.count)} ${unit}`
    : 'Hover or focus a band to read it. Ribbon width is proportional to the count.'

  return (
    <figure className="sankey" style={{ '--c': color }}>
      <div className="sankey-scroll" tabIndex={0} role="group" aria-label={label || 'Sankey diagram of flows, scrolls sideways on small screens'}>
        <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label || 'Sankey diagram of flows between groups'}>
          <g className="ribbons">
            {graph.links.map((l, i) => {
              const x0 = l.a.x + NODE_W, x1 = l.b.x, mx = (x0 + x1) / 2
              const dim = active && active !== l
              return (
                <path key={i} d={`M${x0} ${l.y0} C${mx} ${l.y0}, ${mx} ${l.y1}, ${x1} ${l.y1}`} strokeWidth={l.t}
                  className={'ribbon' + (active === l ? ' on' : '') + (dim ? ' dim' : '')}
                  tabIndex="0" aria-label={`${l.from} to ${l.to}, ${show(l.count)} ${unit}`}
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(i)} onBlur={() => setHover(null)} />
              )
            })}
          </g>
          {graph.nodes.map(n => {
            const lit = !active || touches(active, n.name)
            const left = false
            return (
              <g key={n.name} className={'snode' + (lit ? '' : ' dim')}>
                <rect x={n.x} y={n.y} width={NODE_W} height={n.h} />
                <text x={left ? n.x - 8 : n.x + NODE_W + 8} y={n.y + n.h / 2 - 2} textAnchor={left ? 'end' : 'start'} className="s-name">{clip(n.name)}</text>
                <text x={left ? n.x - 8 : n.x + NODE_W + 8} y={n.y + n.h / 2 + 12} textAnchor={left ? 'end' : 'start'} className="s-count">{show(n.value)}</text>
              </g>
            )
          })}
        </svg>
      </div>
      <figcaption aria-live="polite">{caption}</figcaption>
      <details className="sankey-table">
        <summary>Read as a table</summary>
        <div className="table-scroll">
          <table>
            <thead><tr><th>From</th><th>To</th><th>{unit[0].toUpperCase() + unit.slice(1)}</th></tr></thead>
            <tbody>{graph.links.map((l, i) => <tr key={i}><td>{l.from}</td><td>{l.to}</td><td>{show(l.count)}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </figure>
  )
}
