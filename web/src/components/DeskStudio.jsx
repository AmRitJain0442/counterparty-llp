import React, { useEffect, useRef, useState } from 'react'
import { DESKS, DESK_BY_ID, subjectSpec, executiveProblem } from '../desks'
import { streamCase } from '../streamCase'
import FlowDiagram from './FlowDiagram'
import './studio.css'

export default function DeskStudio({ deskId, onDeskChange, onFiled }) {
  const desk = DESK_BY_ID[deskId]
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
  const subjectText = subjectSpec(desk)
  const execProblem = deskId === 'company' ? executiveProblem(values) : ''
  const needsConsent = (desk.alwaysConsent || desk.consentFor?.some(k => (values[k] || '').trim()))
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
    if (!subject.trim()) { setError(subjectText.error); return }
    if (execProblem) { setError(execProblem); document.getElementById('company-executive_name')?.focus(); return }
    abort.current?.abort()
    abort.current = new AbortController()
    setBusy(true)
    setActivity({})
    try {
      const cleaned = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, (v || '').trim()]).filter(([, v]) => v))
      const intake = {
        desk: deskId, mode: 'live', subject: subject.trim(), consent: needsConsent ? consent : false, inputs: cleaned,
      }
      const filed = await streamCase(intake, event => setActivity(items => ({ ...items, [event.name]: event.status })), abort.current.signal)
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

          <label className="field">
            <span>{subjectText.label}</span>
            <input id={`subject-${deskId}`} value={subject} maxLength={180} required
              placeholder={subjectText.placeholder}
              onChange={e => setSubjects(all => ({ ...all, [deskId]: e.target.value }))} />
          </label>

          {desk.fields.map(f => (
            <label key={f.key} className="field">
              <span>{f.label}{f.required ? '' : <em> optional</em>}</span>
              {f.long
                ? <textarea id={`${deskId}-${f.key}`} rows={3} maxLength={2000} value={values[f.key] || ''} required={f.required}
                    placeholder={f.placeholder} onChange={e => setValue(f.key, e.target.value)} />
                : <input id={`${deskId}-${f.key}`} maxLength={300} value={values[f.key] || ''} required={f.required}
                    aria-invalid={f.key === 'executive_name' && !!execProblem} aria-describedby={f.hint ? `${deskId}-${f.key}-hint` : undefined}
                    placeholder={f.placeholder} onChange={e => setValue(f.key, e.target.value)} />}
              {f.hint && <small className="hint" id={`${deskId}-${f.key}-hint`}>{f.hint}</small>}
              {f.key === 'executive_name' && execProblem && <small className="hint warn" role="alert">{execProblem}</small>}
            </label>
          ))}

          {needsConsent && (
            <label className="consent">
              <input type="checkbox" id={`consent-${deskId}`} required checked={consent}
                onChange={e => setConsents(all => ({ ...all, [deskId]: e.target.checked }))} />
              <span>The person has agreed to this profile check. Without consent the desk cannot read their record.</span>
            </label>
          )}

          <div className="submit-row">
            <button type="submit" className="btn primary" disabled={busy}>
              {busy ? 'Collecting evidence…' : `Open a live ${desk.name} case`}
            </button>
            <span className="fine">Findings are requests for explanation. A person makes the call.</span>
          </div>
          {busy && <p className="status" role="status">Collecting live evidence. Providers report back below as each step finishes.</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </form>

        <div className="flow">
          <div className="flow-head">
            <span className="label">Data flow</span>
            <span className="fine">Fields light up as you fill them. Nothing is sent until you open the case.</span>
          </div>
          <div className="flow-scroll" tabIndex={0} role="group" aria-label="Data flow diagram, scrolls sideways on small screens">
            <FlowDiagram desk={desk} values={values} />
          </div>
          {busy && Object.keys(activity).length > 0 && <div className="live-feed" aria-label="Live collection events">
            {Object.entries(activity).map(([name,status]) => <div key={name}><span>{name.replaceAll('_',' ')}</span><b>{status}</b></div>)}
          </div>}
          <dl className="fee">
            <div><dt>Replaces</dt><dd>{desk.replaces}</dd></div>
            <div><dt>Human fee</dt><dd>{desk.fee}</dd></div>
            <div><dt>Crustdata estimate</dt><dd>{desk.credits} credits</dd></div>
            <div><dt>Gemini analysis</dt><dd>Up to 28 reviews on Vertex AI</dd></div>
          </dl>
        </div>
      </div>
    </div>
  )
}
