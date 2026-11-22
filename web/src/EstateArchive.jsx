import React, {useEffect, useState} from 'react'

export default function EstateArchive() {
  const [record,setRecord]=useState(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    const abort=new AbortController()
    fetch('/api/exhibits/older-estate',{signal:abort.signal}).then(r=>{
      if(!r.ok) throw new Error()
      return r.json()
    }).then(setRecord).catch(e=>{if(e.name!=='AbortError')setError('Archived evidence unavailable.')})
    return ()=>abort.abort()
  },[])
  return <section className="live-bench">
    <small>ESTATE ARCHIVE</small><h1>{record?.subject || 'Estate reconstruction'}</h1>
    {!record ? <p>{error || 'Reading the cached exhibit…'}</p> : <>
      <p>CACHED · {new Date(record.as_of).toLocaleDateString()} · {record.credits} credits at collection</p>
      <h2>{record.verdict}</h2><p>{record.summary}</p>
      <div className="bench-trace">{record.flows.map(flow=><div className="trace-line" key={flow.to}>
        <span>{flow.from} → {flow.to}</span><b>{flow.count} profiles</b>
      </div>)}</div>
      {record.evidence.map((e,i)=><article key={i}><h3>{e.label.replaceAll('_',' ')}</h3>
        <p>{e.detail}</p><a href={e.url} target="_blank" rel="noreferrer">{e.source} ↗</a>
      </article>)}
    </>}
  </section>
}
