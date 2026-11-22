import React, { useEffect, useRef, useState } from 'react'
import { DESKS, DESK_BY_ID } from '../desks'
import { createCase } from '../api'
import { streamCase } from '../streamCase'
import FlowDiagram from './FlowDiagram'
import './studio.css'

const DEMO_NOTE = {
  payment: 'A seeded vendor email asks for new bank details. The named contact has left the vendor, the sending domain is days old and the IFSC points at a different bank.',
  candidate: 'A synthetic candidate claims to have led 40 engineers. The employer’s dated engineering headcount for that quarter says otherwise.',
  estate: 'A Norwegian contractor has gone bankrupt. The case traces where its staff went and tests one shared-board hit against the opposing-counsel filter.',
  company: 'A US-listed issuer’s latest 8-K items are read next to dated leadership and finance moves, then a forward prediction is signed.',
}

export default function DeskStudio({ deskId, onDeskChange, onFiled }) {
  const desk = DESK_BY_ID[deskId]
  const [mode, setMode] = useState('demo')
  const [subjects, setSubjects] = useState({})
  const [inputs, setInputs] = useState({})
  const [consents, setConsents] = useState({})
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState({})
  const [error, setError] = useState('')
  const abort = useRef(null)
  useEffect(() => () => abort.current?.abort(), [])

  const values = inputs[deskId] || {}
  const subject = subjects[deskId] || ''
  const consent = !!consents[deskId]
  const needsConsent = mode === 'live' && (desk.alwaysConsent || desk.consentFor?.some(k => (values[k] || '').trim()))
  const setValue = (key, value) => setInputs(all => ({ ...all, [deskId]: { ...all[deskId], [key]: value } }))

  function onTabKey(event) {
    const i = DESKS.findIndex(d => d.id === deskId)
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const next = DESKS[(i + step + DESKS.length) % DESKS.length]
    onDeskChange(next.id)
    document.getElementById('tab-' + next.id)?.focus()
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (mode === 'live' && !subject.trim()) { setError('Enter who or what this live inquiry is about.'); return }
    abort.current?.abort()
    abort.current = new AbortController()
    setBusy(true)
    setActivity({})
    try {
      const cleaned = mode === 'live'
        ? Object.fromEntries(Object.entries(values).map(([k, v]) => [k, (v || '').trim()]).filter(([, v]) => v))
        : {}
      const intake = {
        desk: deskId, mode, subject: subject.trim(), consent: needsConsent ? consent : false, inputs: cleaned,
      }
      const filed = mode === 'demo' ? await createCase(intake, abort.current.signal)
        : await streamCase(intake, event => setActivity(items => ({ ...items, [event.name]: event.status })), abort.current.signal)
      onFiled(filed)
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="studio" style={{ '--c': desk.color }}>
      <div className="tabs" role="tablist" aria-label="Desks" onKeyDown={onTabKey}>
        {DESKS.map(d => (
          <button key={d.id} id={'tab-' + d.id} role="tab" type="button" aria-selected={d.id === deskId} aria-controls="desk-panel"
            tabIndex={d.id === deskId ? 0 : -1} onClick={() => onDeskChange(d.id)} style={{ '--c': d.color }}>
            <span className="swatch" aria-hidden="true" />
            <b>{d.name}</b><small>{d.alias}</small>
          </button>
        ))}
      </div>

      <div className="panel" id="desk-panel" role="tabpanel" aria-labelledby={'tab-' + deskId}>
        <form onSubmit={submit} className="intake" noValidate={false}>
          <header>
            <span className="label">{desk.alias}</span>
            <h3>{desk.question}</h3>
          </header>

          <div className="mode" role="radiogroup" aria-label="Run mode">
            {[['demo', 'Demo', 'Seeded case, no subject needed'], ['live', 'Live', 'Real providers, metered credits']].map(([id, name, hint]) => (
              <label key={id} className={mode === id ? 'on' : ''}>
                <input type="radio" name="mode" value={id} checked={mode === id} onChange={() => { setMode(id); setError('') }} />
                <b>{name}</b><small>{hint}</small>
              </label>
            ))}
          </div>

          <label className="field">
            <span>{mode === 'live' ? 'Subject' : 'Subject (optional)'}</span>
            <input id={`subject-${deskId}`} value={subject} maxLength={180} required={mode === 'live'}
              placeholder={mode === 'live' ? 'The company or person being checked' : 'Leave blank to use the seeded case'}
              onChange={e => setSubjects(all => ({ ...all, [deskId]: e.target.value }))} />
          </label>

          {mode === 'live' ? desk.fields.map(f => (
            <label key={f.key} className="field">
              <span>{f.label}{f.required ? '' : <em> optional</em>}</span>
              {f.long
                ? <textarea id={`${deskId}-${f.key}`} rows={3} maxLength={2000} value={values[f.key] || ''} required={f.required}
                    placeholder={f.placeholder} onChange={e => setValue(f.key, e.target.value)} />
                : <input id={`${deskId}-${f.key}`} maxLength={300} value={values[f.key] || ''} required={f.required}
                    placeholder={f.placeholder} onChange={e => setValue(f.key, e.target.value)} />}
            </label>
          )) : <p className="demo-note">{DEMO_NOTE[deskId]}</p>}

          {needsConsent && (
            <label className="consent">
              <input type="checkbox" id={`consent-${deskId}`} required checked={consent}
                onChange={e => setConsents(all => ({ ...all, [deskId]: e.target.checked }))} />
              <span>The person has agreed to this profile check. Without consent the desk cannot read their record.</span>
            </label>
          )}

          <div className="submit-row">
            <button type="submit" className="btn primary" disabled={busy}>
              {busy ? 'Collecting evidence…' : mode === 'demo' ? `Run the ${desk.name} demo` : `Open a live ${desk.name} case`}
            </button>
            <span className="fine">Findings are requests for explanation. A person makes the call.</span>
          </div>
          {busy && <p className="status" role="status">Collecting the case evidence?</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </form>

        <div className="flow">
          <div className="flow-head">
            <span className="label">Data flow</span>
            <span className="fine">{mode === 'live' ? 'Fields light up as you fill them.' : 'Demo reads a seeded case; live reads these routes.'}</span>
          </div>
          <div className="flow-scroll" tabIndex={0} role="group" aria-label="Data flow diagram, scrolls sideways on small screens">
            <FlowDiagram desk={desk} values={values} mode={mode} />
          </div>
          {busy && Object.keys(activity).length > 0 && <div className="live-feed" aria-label="Live collection events">
            {Object.entries(activity).map(([name,status]) => <div key={name}><span>{name.replaceAll('_',' ')}</span><b>{status}</b></div>)}
          </div>}
          <dl className="fee">
            <div><dt>Replaces</dt><dd>{desk.replaces}</dd></div>
            <div><dt>Human fee</dt><dd>{desk.fee}</dd></div>
            <div><dt>{mode === 'demo' ? 'Demo cost' : 'Live budget estimate'}</dt><dd>{mode === 'demo' ? 0 : desk.credits} credits</dd></div>
          </dl>
        </div>
      </div>
    </div>
  )
}
