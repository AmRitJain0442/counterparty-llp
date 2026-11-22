import React from 'react'

/** Interlocking witness mark: two offset chevrons around a diamond (the verdict). */
export function Mark({ size = 28, title }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role={title ? 'img' : undefined}
      aria-label={title} aria-hidden={title ? undefined : true} className="mark">
      <g fill="none" stroke="currentColor" strokeWidth="4.5" strokeLinecap="square" strokeLinejoin="miter">
        <path d="M38 14H25L12 32l13 18h13" />
        <path d="M26 14h13l13 18-13 18H26" opacity=".64" />
        <path d="m24 32 8-11 8 11-8 11z" />
      </g>
    </svg>
  )
}

export default function Logo() {
  return (
    <span className="logo">
      <Mark size={30} />
      <span className="logo-word">Counterparty</span>
      <span className="logo-llp">LLP</span>
    </span>
  )
}
