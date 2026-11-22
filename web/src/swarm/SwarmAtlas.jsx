import React, { useEffect, useRef, useState } from 'react'
import SwarmMap from './SwarmMap'
import Inspector from './Inspector'
import { DESKS, executiveProblem } from '../desks'
import { Mark } from '../components/Logo'
import { streamCase } from '../streamCase'
import './atlas.css'

export default function SwarmAtlas({onFile,desk,onDesk,cases=[]}) {
  const [liveRoster,setLiveRoster]=useState([])
  const [selected,setSelected]=useState(null)
  const [panel,setPanel]=useState(()=>window.innerWidth>=900)
  const [section,setSection]=useState('agents')
  const [events,setEvents]=useState([])
  const [record,setRecord]=useState(null)
  const [subject,setSubject]=useState('')
  const [inputs,setInputs]=useState({})
  const [consent,setConsent]=useState(false)
  const [running,setRunning]=useState(false)
  const [error,setError]=useState('')
  const [playing,setPlaying]=useState(()=>!window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [playhead,setPlayhead]=useState(null)
  const [search,setSearch]=useState(null)
  const inflight=useRef(null)
  const inputRef=useRef(null)
  const requestedCase=useRef(new URLSearchParams(location.search).get('case'))
  const agents=React.useMemo(()=>{
    if (!record) return liveRoster
    if (Array.isArray(record.swarm_roster)) return record.swarm_roster
    // Older cases recorded reports and events, before roster snapshots existed.
    return (record.swarm_reports || []).map(report=>{
      const start=record.swarm_events?.find(e=>e.agent_id===report.agent_id && e.event==='start')
      const known=liveRoster.find(a=>a.id===report.agent_id)
      return {...report,id:report.agent_id,name:report.name||start?.name||known?.name||report.agent_id,
        group:report.group||start?.group||known?.group,depends_on:report.depends_on||start?.depends_on,
        task:start?.detail}
    })
  },[record,liveRoster])
  const active=agents.find(a=>a.id===selected)
  const trace=playhead===null?events:events.slice(0,playhead)
  const visibleEvents=trace.filter(e=>e.agent_id||e.collection_agent)
  const specialists=agents.filter(a=>a.parent_id).length
  const matches=search===null?[]:agents.filter(a=>[a.name,a.persona,a.group].some(value=>
    value?.toLowerCase().includes(search.trim().toLowerCase())))
  const idle=!running&&!record&&events.length===0
  useEffect(()=>{
    const controller=new AbortController()
    inflight.current?.abort();inflight.current=null;setRunning(false)
    setLiveRoster([]);setSelected(null);setInputs({});setConsent(false);setSubject('');setEvents([]);setRecord(null);setError('');setPlayhead(null)
    fetch('/api/swarms/'+desk,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('The agent roster could not be opened.');return r.json()})
      .then(r=>{if(!controller.signal.aborted)setLiveRoster(r.agents)}).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return ()=>controller.abort()
  },[desk])
  useEffect(()=>()=>{
    inflight.current?.abort()
  },[])
  useEffect(()=>{
    if(!playing||playhead===null)return
    if(playhead>=events.length){if(!running)setPlayhead(null);return}
    const timer=setTimeout(()=>setPlayhead(n=>n===null?null:n+1),145)
    return ()=>clearTimeout(timer)
  },[playing,playhead,events.length,running])
  useEffect(()=>{
    function key(e) {
      if(e.key==='Escape'){if(search!==null)setSearch(null);else {setPanel(false);setSelected(null)}}
      if((e.key==='f'||e.key==='/')&&!e.metaKey&&!e.ctrlKey&&!e.altKey&&!/input|textarea|select/i.test(e.target.tagName)){
        e.preventDefault();setSearch('')
      }
    }
    window.addEventListener('keydown',key)
    return ()=>window.removeEventListener('keydown',key)
  },[search])
  const searching=search!==null
  useEffect(()=>{
    if(!searching)return
    const previous=document.activeElement
    inputRef.current?.focus()
    return ()=>previous?.focus?.({preventScroll:true})
  },[searching])
  function inspect(id) {setSelected(id);setPanel(true);setSection('agents');setSearch(null)}
  async function run(){
    if(inflight.current)return
    const problem=desk==='company'?executiveProblem(inputs):''
    if(problem){setError(problem);setPanel(true);setSection('run');return}
    const controller=new AbortController()
    inflight.current=controller
    setRunning(true);setSelected(null);setError('');setRecord(null);setEvents([]);setPlayhead(null);setPanel(true);setSection('trace')
    try {
      const result=await streamCase({desk,mode:'live',subject:subject.trim(),consent,inputs},e=>{if(!controller.signal.aborted)setEvents(items=>[...items,e])},controller.signal)
      if(!controller.signal.aborted){setRecord(result);onFile?.(result)}
    }catch(e){if(e.name!=='AbortError')setError(e.message)}
    finally{if(inflight.current===controller){inflight.current=null;setRunning(false)}}
  }
  function saved(id) {
    const found=cases.find(c=>c.id===id)
    if(!found||running)return
    setSelected(null);setRecord(found);setEvents([...(found.collection_events||[]),...(found.swarm_events||[])]);setPlayhead(playing?0:null);setSection('trace')
  }
  useEffect(()=>{
    if(!requestedCase.current) return
    const found=cases.find(c=>c.id===requestedCase.current)
    if(!found) return
    if(found.desk!==desk){onDesk(found.desk);return}
    requestedCase.current=null
    saved(found.id)
    setPanel(true)
  },[cases,desk,onDesk])
  function replay(){if(!events.length)return;setPlaying(true);setPlayhead(0)}
  return <section id="swarm" className={'atlas'+(panel?' inspect-open':'')+(selected?' agent-focus':'')} aria-label="Agent swarm workflow">
    <header className="atlas-top">
      <nav aria-label="Workflow views"><a href="#swarm" className="current">Swarm map</a><a href="#desks">Desks</a><a href="#ledger">Ledger</a></nav>
      <a href="#swarm" className="atlas-brand"><Mark size={21}/> COUNTERPARTY <em>LLP</em></a>
      <div className="atlas-tools"><button onClick={()=>setSearch('')}>Find <kbd>F</kbd></button><button onClick={()=>{setPanel(v=>!v);if(panel)setSelected(null);setSection('agents')}} aria-expanded={panel}>Inspector</button></div>
    </header>
    <div className="atlas-layout">
      <div className="atlas-field">
        <div className="atlas-crumb">Firm <span>/</span> {DESKS.find(d=>d.id===desk)?.name} desk <span>/</span> <b>Swarm map</b></div>
        <SwarmMap agents={agents} selected={selected} onSelect={inspect} events={visibleEvents} reports={playhead===null?record?.swarm_reports:undefined} running={running} idle={idle} recorded={!!record} playing={playing} onToggle={()=>{if(!playing&&record&&playhead===null)replay();else setPlaying(v=>!v)}}/>
        <div className="atlas-caption"><h1>Counterparty investigation map.</h1>
          <p>{specialists?'Select a lead or its paired specialists to inspect their findings.':'Select an agent to trace its witnesses, handoffs and findings.'}</p>
          <button onClick={()=>{setPanel(true);setSection('run')}}>Open an investigation ↗</button>
        </div>
        <div className="atlas-counts">{specialists>0?<><span>leads<b>{agents.length-specialists}</b></span><span>specialists<b>{specialists}</b></span></>:<span>agents<b>{agents.length||'—'}</b></span>}<span>desk<b>{desk}</b></span></div>
      </div>
      {panel&&<div className="atlas-dock"><Inspector {...{desk,agents,events:trace,running,record,subject,setSubject,inputs,setInputs,consent,setConsent,error,
        section,setSection,onReplay:replay,replaying:playhead!==null}} agent={active} onSelect={inspect} onClose={()=>{setPanel(false);setSelected(null)}} onRun={run}
        onDesk={v=>{if(!running)onDesk(v)}} caseOptions={cases.filter(c=>c.desk===desk&&(c.swarm_events?.length||c.swarm_reports?.length)).map(c=>({id:c.id,label:c.subject+' · '+c.id.slice(0,6)}))} onCase={saved}/></div>}
    </div>
    {error&&!panel&&<p role="alert">{error}</p>}
    {search!==null&&<div className="atlas-search" onClick={()=>setSearch(null)}><div role="dialog" aria-modal="true" aria-label="Find an agent" onClick={e=>e.stopPropagation()}
      onKeyDown={e=>{
        if(e.key!=='Tab')return
        const controls=e.currentTarget.querySelectorAll('input,button')
        const first=controls[0],last=controls[controls.length-1]
        if(e.shiftKey&&e.target===first){e.preventDefault();last.focus()}
        else if(!e.shiftKey&&e.target===last){e.preventDefault();first.focus()}
      }}>
      <label>Find an agent<input ref={inputRef} value={search} onChange={e=>setSearch(e.target.value)}
        onKeyDown={e=>{if(e.key==='Enter'&&matches.length===1)inspect(matches[0].id)}} placeholder="Search name, persona or swarm"/></label>
      <button onClick={()=>setSearch(null)}>Close</button>
      <ul>{matches.map(a=><li key={a.id}><button onClick={()=>inspect(a.id)}>
        <strong>{a.name}</strong><small>{a.parent_id?'Specialist · '+agents.find(p=>p.id===a.parent_id)?.name:specialists?'Lead · '+a.group:a.group}</small>
        {a.persona&&<span>{a.persona}</span>}
      </button></li>)}</ul>
      {!matches.length&&<p>No matching agents.</p>}
    </div></div>}
  </section>
}
