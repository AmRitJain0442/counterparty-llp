import React, { useState } from 'react'
import { streamCase } from './streamCase'

const names = {payment:'Payment',candidate:'Candidate',estate:'Estate',company:'Company'}
const fields = {
  payment:[['domain','Vendor domain'],['sender_domain','Sending domain'],['person_url','Consented profile URL'],['orgnr','Vendor registry number (Norway)'],['ifsc','New bank IFSC']],
  candidate:[['person_url','Candidate profile URL'],['domain','Claimed employer domain'],['claim','Employment claim']],
  estate:[['domain','Company domain'],['orgnr','Norwegian registry number']],
  company:[['domain','Company domain'],['cik','SEC CIK'],['lei','Legal entity identifier'],['claim','Question to investigate']],
}

export default function LiveWorkbench({startDesk='estate'}) {
  const [desk,setDesk]=useState(startDesk)
  const [subject,setSubject]=useState('')
  const [inputs,setInputs]=useState({})
  const [consent,setConsent]=useState(false)
  const [events,setEvents]=useState([])
  const [busy,setBusy]=useState(false)
  const [record,setRecord]=useState(null)
  const [error,setError]=useState('')
  function choose(value) {
    setDesk(value);setSubject('');setInputs({});setConsent(false);setEvents([]);setRecord(null);setError('')
  }
  async function submit(e) {
    e.preventDefault()
    setBusy(true);setEvents([]);setError('');setRecord(null)
    try {
      const result=await streamCase({desk,mode:'live',subject,inputs,consent},step=>setEvents(all=>[...all,step]))
      setRecord(result)
    } catch(ex){setError(ex.message)}
    finally{setBusy(false)}
  }
  const lanes=Object.values(events.reduce((acc,ev)=>({...acc,[ev.name]:ev}),{}))
  return <section className="live-bench">
    <header><small>PROVIDER WORKSPACE</small><h1>Live investigation</h1><p>Every run here queries live providers and spends metered credits. Trace collection, challenge and filing as each desk reports back.</p></header>
    <div className="bench-grid"><form onSubmit={submit}><fieldset disabled={busy}>
      <label>Desk<select value={desk} onChange={e=>choose(e.target.value)}>{Object.entries(names).map(([id,n])=><option key={id} value={id}>{n}</option>)}</select></label>
      <label>Subject<input required value={subject} maxLength={180} onChange={e=>setSubject(e.target.value)} /></label>
      {fields[desk].map(([key,label])=><label key={key}>{label}<input value={inputs[key]||''} required={desk==='candidate' && ['person_url','domain','claim'].includes(key)}
        onChange={e=>setInputs({...inputs,[key]:e.target.value})} /></label>)}
      {(desk==='candidate'||desk==='payment'&&inputs.person_url)&&<label className="consent"><input type="checkbox" required checked={consent} onChange={e=>setConsent(e.target.checked)}/> I have permission for this profile check.</label>}
      <button type="submit">{busy?'Collecting evidence…':'Run live investigation ↗'}</button>
    </fieldset></form>
    <div className="bench-trace" aria-live="polite"><small>COLLECTION LOG</small>
      {!events.length && <p>{busy?'Opening the case…':'The collection log opens when the investigation starts.'}</p>}
      {lanes.map(row=><div key={row.name} className="trace-line"><span>{row.name.replaceAll('_',' ')}</span><b>{row.status}</b></div>)}
      {error && <p role="alert">{error}</p>}
      {record && <article><small>FILED DECISION</small><h2>{record.verdict}</h2><p>{record.summary}</p>
        <p>{record.draft}</p><div>{record.evidence.map((row,i)=><details key={i}><summary>{row.label}</summary><p>{row.detail}</p>
          {row.url && /^https?:\/\//.test(row.url) && <a href={row.url} rel="noreferrer" target="_blank">Open source ↗</a>}</details>)}</div>
        <p>{record.credits??'Unknown'} credits · Receipt <code>{record.receipt.slice(0,16)}</code></p></article>}
    </div></div></section>
}
