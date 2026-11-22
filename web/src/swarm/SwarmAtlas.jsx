import React, { useEffect, useRef, useState } from 'react'
import SwarmMap from './SwarmMap'
import Inspector from './Inspector'
import { DESKS } from '../desks'
import { Mark } from '../components/Logo'
import { streamCase } from '../streamCase'
import './atlas.css'

export default function SwarmAtlas({onFile,desk,onDesk,cases=[]}) {
  const [agents,setAgents]=useState([])
  const [selected,setSelected]=useState(null)
  const [panel,setPanel]=useState(()=>window.innerWidth>=1050)
  const [section,setSection]=useState('agents')
  const [events,setEvents]=useState([])
  const [record,setRecord]=useState(null)
  const [mode,setMode]=useState('demo')
  const [subject,setSubject]=useState('')
  const [inputs,setInputs]=useState({})
  const [consent,setConsent]=useState(false)
  const [running,setRunning]=useState(false)
  const [error,setError]=useState('')
  const [playing,setPlaying]=useState(()=>!window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [playhead,setPlayhead]=useState(null)
  const [search,setSearch]=useState(null)
  const [runMode,setRunMode]=useState('demo')
  const inflight=useRef(null)
  const inputRef=useRef(null)
  const requestedCase=useRef(new URLSearchParams(location.search).get('case'))
  const active=agents.find(a=>a.id===selected)
  const trace=playhead===null?events:events.slice(0,playhead)
  const visibleEvents=trace.filter(e=>e.agent_id||e.collection_agent)
  const groupCount=new Set(agents.map(a=>a.group)).size
  const preview=!running&&!record&&events.length===0
  useEffect(()=>{
    const controller=new AbortController()
    inflight.current?.abort();inflight.current=null;setRunning(false)
    setAgents([]);setSelected(null);setInputs({});setConsent(false);setSubject('');setEvents([]);setRecord(null);setError('');setPlayhead(null)
    fetch('/api/swarms/'+desk,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('The agent roster could not be opened.');return r.json()})
      .then(r=>setAgents(r.agents)).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
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
  useEffect(()=>{if(search!==null)inputRef.current?.focus()},[search!==null])
  function inspect(id) {setSelected(id);setPanel(true);setSection('agents');setSearch(null)}
  async function run(){
    if(inflight.current)return
    const controller=new AbortController()
    inflight.current=controller
    setRunning(true);setSelected(null);setRunMode(mode);setError('');setRecord(null);setEvents([]);setPlayhead(mode==='demo'&&playing?0:null);setPanel(true);setSection('trace')
    try {
      const result=await streamCase({desk,mode,subject,consent,inputs},e=>{if(!controller.signal.aborted)setEvents(items=>[...items,e])},controller.signal)
      if(!controller.signal.aborted){setRecord(result);onFile?.(result)}
    }catch(e){if(e.name!=='AbortError')setError(e.message)}
    finally{if(inflight.current===controller){inflight.current=null;setRunning(false)}}
  }
  function saved(id) {
    const found=cases.find(c=>c.id===id)
    if(!found||running)return
    setSelected(null);setRecord(found);setRunMode(found.mode);setEvents([...(found.collection_events||[]),...(found.swarm_events||[])]);setPlayhead(playing?0:null);setSection('trace')
  }
  useEffect(()=>{
    if(!requestedCase.current || !agents.length) return
    const found=cases.find(c=>c.id===requestedCase.current)
    if(!found) return
    if(found.desk!==desk){onDesk(found.desk);return}
    requestedCase.current=null
    saved(found.id)
    setPanel(true)
  },[cases,desk,agents,onDesk])
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
        <SwarmMap agents={agents} selected={selected} onSelect={inspect} events={visibleEvents} reports={playhead===null?record?.swarm_reports:undefined} running={running} preview={preview} playing={playing} onToggle={()=>{if(!playing&&record&&playhead===null)replay();else setPlaying(v=>!v)}}/>
        <div className="atlas-caption"><h1>Counterparty investigation map.</h1>
          <p>Select an agent to trace its witnesses, handoffs and findings.</p>
          <button onClick={()=>{setPanel(true);setSection('run')}}>Open an investigation ↗</button>
        </div>
        <div className="atlas-counts"><span>swarms<b>{groupCount||'—'}</b></span><span>agents<b>{agents.length||'—'}</b></span><span>desk<b>{desk}</b></span></div>
      </div>
      {panel&&<div className="atlas-dock"><Inspector {...{desk,agents,events:trace,running,record,mode,setMode,subject,setSubject,inputs,setInputs,consent,setConsent,error,
        section,setSection,onReplay:replay,runMode,replaying:playhead!==null}} agent={active} onSelect={inspect} onClose={()=>{setPanel(false);setSelected(null)}} onRun={run}
        onDesk={v=>{if(!running)onDesk(v)}} caseOptions={cases.filter(c=>c.desk===desk&&c.swarm_events?.length).map(c=>({id:c.id,label:c.subject+' · '+c.id.slice(0,6)}))} onCase={saved}/></div>}
    </div>
    {error&&!panel&&<p role="alert">{error}</p>}
    {search!==null&&<div className="atlas-search" onClick={()=>setSearch(null)}><div role="dialog" aria-modal="true" aria-label="Find an agent" onClick={e=>e.stopPropagation()}>
      <label>Find an agent<input ref={inputRef} value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search agents or swarms"/></label>
      <button onClick={()=>setSearch(null)}>Close</button>
      <ul>{agents.filter(a=>(a.name+' '+a.group).toLowerCase().includes(search.toLowerCase())).map(a=><li key={a.id}><button onClick={()=>inspect(a.id)}>{a.name}<small>{a.group}</small></button></li>)}</ul>
    </div></div>}
  </section>
}
