import React, { useEffect, useMemo, useState } from 'react'
import { DESKS } from '../desks'
import './map.css'

/*
 * The firm as a transit map. Four desk lines leave their own intake, share two
 * interchanges (identity spine, counsel and partner) and each end at a verdict.
 * Geometry is computed once from row positions so the bends stay at 45 degrees.
 */
const W = 1260, H = 420, CY = 210
const ROWS = [70, 163, 257, 350]
const X = { start: 40, spine: [290, 360], witness: 560, counsel: [790, 850], end: 1058 }
const WITNESS = [['Crustdata', 'RDAP · IFSC'], ['Crustdata', 'colleagues'], ['Brønnøysund', 'Crustdata'], ['EDGAR 8-K', 'Crustdata']]
const TERMINAL = [['HELD', 'RELEASED'], ['FAILED', 'VERIFIED'], ['REQUEST FOR EXPLANATION', 'KILLED'], ['SIGNED', 'FORECAST']]

function route(i) {
  const ry = ROWS[i]
  const lane = CY + (i - 1.5) * 9
  const d1 = Math.abs(lane - ry)
  return [
    `M${X.start} ${ry}`, `H${X.spine[0] - d1}`, `L${X.spine[0]} ${lane}`, `H${X.spine[1]}`,
    `L${X.spine[1] + d1} ${ry}`, `H${X.counsel[0] - d1}`, `L${X.counsel[0]} ${lane}`, `H${X.counsel[1]}`,
    `L${X.counsel[1] + d1} ${ry}`, `H${X.end}`,
  ].join(' ')
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return reduced
}

export default function FirmMap({ onOpen }) {
  const [focus, setFocus] = useState(0)
  const reduced = usePrefersReducedMotion()
  const paths = useMemo(() => ROWS.map((_, i) => route(i)), [])
  const desk = DESKS[focus]
  const above = i => i < 2

  return (
    <div className="firm-map">
      <div className="map-frame">
        <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Map of the four desks, their shared review stations and their verdicts">
          <defs>
            <pattern id="mapDots" width="22" height="22" patternUnits="userSpaceOnUse">
              <circle cx="1.5" cy="1.5" r="1" fill="#322f25" />
            </pattern>
          </defs>
          <rect width={W} height={H} fill="url(#mapDots)" />

          {[X.spine, X.counsel].map(([a, b], k) => (
            <g key={k}>
              <rect x={a - 10} y={CY - 38} width={b - a + 20} height={76} rx="38" className="interchange" />
              <text x={(a + b) / 2} y={CY + 60} textAnchor="middle" className="station-label">
                {k === 0 ? 'IDENTITY SPINE' : 'COUNSEL · PARTNER'}
              </text>
            </g>
          ))}

          {DESKS.map((d, i) => {
            const active = i === focus
            const ry = ROWS[i]
            const open = () => onOpen(d.id)
            return (
              <g key={d.id} className={'line' + (active ? ' on' : '')} style={{ '--c': d.color }}
                tabIndex="0" role="button" aria-label={`${d.name} desk. ${d.question} Open the intake form.`}
                onMouseEnter={() => setFocus(i)} onFocus={() => setFocus(i)} onClick={open}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }}>
                <path d={paths[i]} className="hit" />
                <path id={`route-${d.id}`} d={paths[i]} className="track" />

                <circle cx={X.start} cy={ry} r="7" className="stop" />
                <text x={X.start} y={ry + (above(i) ? -34 : 24)} className="desk-name">{d.name.toUpperCase()}</text>
                <text x={X.start} y={ry + (above(i) ? -19 : 39)} className="desk-alias">{d.alias}</text>

                <circle cx={X.witness} cy={ry} r="6" className="stop" />
                {WITNESS[i].map((line, n) => (
                  <text key={n} x={X.witness} y={ry + (above(i) ? -28 + n * 13 : 22 + n * 13)} textAnchor="middle" className="station-label">{line}</text>
                ))}

                <rect x={X.end - 6} y={ry - 6} width="12" height="12" className="terminal" />
                {TERMINAL[i].map((line, n) => (
                  <text key={n} x={X.end + 16} y={ry - 1 + n * 15} className="verdict-label" style={{ opacity: n ? 0.6 : undefined }}>{line}</text>
                ))}

                {active && !reduced && (
                  <circle r="4.5" className="rider">
                    <animateMotion dur="7s" repeatCount="indefinite" rotate="0">
                      <mpath href={`#route-${d.id}`} />
                    </animateMotion>
                  </circle>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      <div className="map-caption" aria-live="polite" style={{ '--c': desk.color }}>
        <span className="label">{desk.alias}</span>
        <p className="q">{desk.question}</p>
        <p className="replaces">Replaces {desk.replaces.toLowerCase()} ({desk.fee}). About {desk.credits} credits.</p>
        <button type="button" className="btn" onClick={() => onOpen(desk.id)}>Open the {desk.name} desk ↓</button>
      </div>

      <ul className="route-cards" aria-label="The four desks">
        {DESKS.map((d, i) => (
          <li key={d.id} style={{ '--c': d.color }}>
            <button type="button" onClick={() => onOpen(d.id)}>
              <span className="label">{d.alias}</span>
              <b>{d.name} desk</b>
              <span className="q">{d.question}</span>
              <span className="end">{TERMINAL[i].join(' · ')}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
