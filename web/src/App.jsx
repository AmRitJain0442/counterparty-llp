import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Logo from './components/Logo'
import SwarmAtlas from './swarm/SwarmAtlas'
import DeskStudio from './components/DeskStudio'
import CaseFile from './components/CaseFile'
import Sankey, { SPECIMEN_FLOWS } from './components/Sankey'
import Ledger from './components/Ledger'
import { DESK_BY_ID, REVIEW_STAGES } from './desks'
import { getCase, listCases } from './api'
import { formatDate } from './format'
import './app.css'

const RULES = [
  ['Two witnesses', 'An adverse finding needs Crustdata plus one independent record: a registry, a filing or a bank record.'],
  ['Movement is evidence, a stale profile is context', 'An exit is dated by the start date at the next employer. People who never update a profile stay in the unknown group.'],
  ['Aggregates, not people', 'Counts and timelines only, in groups of five or more. Individuals are named only with consent or as statutory officers. Dates of birth are never shown.'],
  ['Requests for explanation', 'No automated legal effect. An adverse result holds the payment or the file and sends a human to call back.'],
  ['Everything is labelled', 'Every row carries an as-of date. Cached data says CACHED and replayed watcher events say REPLAY.'],
]

const WORKSPACE = [
  ['flow', 'Discussion room', 'Follow a filed case from identity to partner review, desk by desk.'],
  ['live', 'Live investigation', 'Stream each collection step as the providers report back.'],
  ['providers', 'Provider room', 'Watch history and the account’s endpoint price card.'],
  ['archive', 'Estate archive', 'Browse dated estate records the desks have filed.'],
]

export default function App() {
  const [deskId, setDeskId] = useState('payment')
  const [cases, setCases] = useState([])
  const [casesLoading, setCasesLoading] = useState(true)
  const [casesError, setCasesError] = useState('')
  const [record, setRecord] = useState(null)
  const [recordLoading, setRecordLoading] = useState(false)
  const [recordError, setRecordError] = useState('')
  const pendingScroll = useRef(null)
  const detailAbort = useRef(null)

  const loadCases = useCallback(signal => {
    setCasesLoading(true)
    setCasesError('')
    listCases(signal)
      .then(rows => setCases(Array.isArray(rows) ? rows : []))
      .catch(e => { if (e.name !== 'AbortError') setCasesError('The ledger could not be opened. ' + e.message) })
      .finally(() => setCasesLoading(false))
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadCases(controller.signal)
    return () => controller.abort()
  }, [loadCases])

  useEffect(() => {
    if (record && pendingScroll.current) {
      pendingScroll.current = null
      document.getElementById('case-file')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [record])

  const onFiled = filed => {
    setRecordError('')
    pendingScroll.current = true
    setRecord(filed)
    setCases(rows => [filed, ...rows.filter(r => r.id !== filed.id)])
  }

  const selectCase = id => {
    detailAbort.current?.abort()
    detailAbort.current = new AbortController()
    setRecordLoading(true)
    setRecordError('')
    pendingScroll.current = true
    getCase(id, detailAbort.current.signal)
      .then(setRecord)
      .catch(e => { if (e.name !== 'AbortError') setRecordError('That case could not be opened. ' + e.message) })
      .finally(() => setRecordLoading(false))
  }

  // The Sankey follows the open case, then the newest filed case that recorded flows.
  const flowCase = useMemo(() => {
    if (record?.flows?.length) return record
    return [...cases].filter(c => c.flows?.length)
      .sort((a, b) => String(b.created_at || b.as_of).localeCompare(String(a.created_at || a.as_of)))[0] || null
  }, [record, cases])
  const flowDesk = flowCase ? DESK_BY_ID[flowCase.desk] : DESK_BY_ID.estate

  return (
    <>
      <SwarmAtlas desk={deskId} onDesk={setDeskId} cases={cases} onFile={filed => {
        setRecordError('')
        setRecord(filed)
        setCases(rows => [filed, ...rows.filter(row => row.id !== filed.id)])
      }} />
      <header className="topbar">
        <div className="wrap">
          <a href="#swarm" aria-label="Counterparty LLP, top of page"><Logo /></a>
          <nav className="nav" aria-label="Sections">
            <a href="#swarm">Swarm map</a>
            <a href="#desks">Desks</a>
            <a href="#flows">Flows</a>
            <a href="#ledger">Ledger</a>
            <a href="#method">Method</a>
            <a href="/workspace.html">Workspace ↗</a>
          </nav>
        </div>
      </header>

      <main id="top">
        <section className="section" id="desks">
          <div className="wrap">
            <div className="section-head">
              <span className="label hot">The desks</span>
              <h2>Pick a desk. Run the seeded case, or open a live one.</h2>
              <p>Demo cases need no input. Live cases ask for the fields each desk reads and show which witnesses they will touch before you send anything.</p>
            </div>
            <DeskStudio deskId={deskId} onDeskChange={setDeskId} onFiled={onFiled} />
            <div className="case-slot">
              <CaseFile record={record} loading={recordLoading} error={recordError} />
            </div>
          </div>
        </section>

        <section className="section" id="flows">
          <div className="wrap">
            <div className="section-head">
              <span className="label hot">Flows</span>
              <h2>{flowCase?.desk === 'estate' ? 'Where an estate’s people went.' : 'How the evidence moved.'}</h2>
              <p>
                {flowCase
                  ? <>From the {flowDesk?.name.toLowerCase()} case <b>{flowCase.subject || 'seeded demonstration'}</b>, filed {formatDate(flowCase.created_at || flowCase.as_of)}. Ribbon width follows the count{flowCase.desk === 'estate' ? '; groups under five are not shown as numbers' : ''}.</>
                  : 'No filed case has recorded flows yet. The layout below is a specimen with invented numbers, so you can see what a filed estate looks like. Run the Estate desk to replace it.'}
              </p>
            </div>
            {flowCase
              ? <Sankey flows={flowCase.flows} color={flowDesk?.color} unit={flowCase.desk === 'estate' ? 'people' : 'signals'} maskSmall={flowCase.desk === 'estate'}
                  label={`Flows for ${flowCase.subject || 'the seeded case'}`} />
              : <div className="specimen"><span className="pill tone-neutral">Specimen · invented numbers</span>
                  <Sankey flows={SPECIMEN_FLOWS} color={DESK_BY_ID.estate.color} label="Specimen layout of an estate’s staff flows" /></div>}
          </div>
        </section>

        <section className="section" id="ledger">
          <div className="wrap">
            <div className="section-head">
              <span className="label hot">Evidence ledger</span>
              <h2>Every case is filed with a receipt.</h2>
              <p>Select a row to reopen its verdict, steps and evidence. The receipt digest can be checked against the ledger at any time.</p>
            </div>
            <Ledger cases={cases} loading={casesLoading} error={casesError} selectedId={record?.id}
              onSelect={selectCase} onRetry={() => loadCases()} />
          </div>
        </section>

        <section className="section" id="method">
          <div className="wrap">
            <div className="section-head">
              <span className="label hot">Method</span>
              <h2>The rules that keep a finding honest.</h2>
              <p>Every desk runs through the same five stations before a verdict reaches the ledger.</p>
            </div>
            <ol className="stages">
              {REVIEW_STAGES.map(([name, note]) => <li key={name}><b>{name}</b><span>{note}</span></li>)}
            </ol>
            <dl className="rules">
              {RULES.map(([t, d]) => <div key={t}><dt>{t}</dt><dd>{d}</dd></div>)}
            </dl>
          </div>
        </section>

        <section className="section" id="workspace">
          <div className="wrap">
            <div className="section-head">
              <span className="label hot">Investigation workspace</span>
              <h2>Go deeper on a case.</h2>
            </div>
            <ul className="rooms">
              {WORKSPACE.map(([id, name, note]) => (
                <li key={id}><a href={'/workspace.html#' + id}><b>{name} ↗</b><span>{note}</span></a></li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <footer className="foot">
        <div className="wrap">
          <Logo />
          <p>Findings are requests for explanation, not accusations. Workers appear as aggregates. A reviewer records any callback or correction.</p>
        </div>
      </footer>
    </>
  )
}
