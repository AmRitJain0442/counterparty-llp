import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useMapCamera } from './useMapCamera'
import './entrance.css'

const EMPTY_REPORTS = []
const C = {identity:'#d9c7a0', discovery:'#a6c1bd', challenge:'#d6a582', decision:'#c3b5bd'}
export const GROUPS = {identity:'Identity', discovery:'Discovery', challenge:'Challenge', decision:'Decision'}
const polar = (a,r) => [450+Math.cos(a)*r,365+Math.sin(a)*r]
const point = p => p.map(n=>n.toFixed(2)).join(',')
const curve = (a,b,c,d) => 'M'+point(a)+' C'+point(b)+' '+point(c)+' '+point(d)
function arc(a,b,r) {
  return 'M'+point(polar(a,r))+' A'+r+','+r+' 0 0 1 '+point(polar(b,r))
}

function geometry(agents, reports) {
  const sorted = Object.keys(GROUPS).flatMap(g=>agents.filter(a=>a.group===g))
  const step=2*Math.PI/Math.max(sorted.length,1)
  return sorted.map((a,i)=>{
    const angle=-Math.PI/2+step*(i+.45)
    const pos=polar(angle,132+(i*17)%21)
    const report=reports.find(r=>r.agent_id===a.id)
    const bandCount=report ? Math.min(8,report.refs.length) : 5
    const strips=Array.from({length:bandCount},(_,k)=>{
      const t=angle+(k-(bandCount-1)/2)*step*.78/Math.max(bandCount,4)
      const w=Math.min(.022+((i+k*7)%9)*.002,step*.25/bandCount)
      const height=31+((i*13+k*17)%49)
      const path=Array.from({length:Math.ceil(height/2.25)},(_,j)=>{
        const r=194+j*2.25
        return 'M'+point(polar(t-w,r))+'L'+point(polar(t+w,r))
      }).join(' ')
      return {path, stem:curve(pos,polar(angle,177),polar(t,168),polar(t,192))}
    })
    return {...a,i,angle,pos,step,strips,report}
  })
}

export default function SwarmMap({agents,selected,onSelect,events,running,preview,playing,onToggle,reports=EMPTY_REPORTS}) {
  const uid=useId().replace(/[^\w-]/g,'')
  const nodes=useMemo(()=>geometry(agents,reports),[agents,reports])
  const index=Object.fromEntries(nodes.map(n=>[n.id,n]))
  const status=Object.fromEntries(events.filter(e=>e.agent_id).map(e=>[e.agent_id,e.status]))
  const collecting=new Map()
  for (const e of events) {
    if(e.collection_agent)collecting.set(e.name,e.status==='running'?e.collection_agent:null)
  }
  const collectors=new Set(collecting.values())
  const edges=useMemo(()=>{
    const result=[]
    for(const target of nodes) {
      const deps=target.depends_on || []
      for(const dep of deps)if(index[dep])result.push([index[dep],target])
    }
    return result
  },[nodes])
  const focusNode=index[selected]
  const svgRef=useRef(null)
  const [compact,setCompact]=useState(()=>window.matchMedia('(max-width:700px)').matches)
  useEffect(()=>{
    const screen=window.matchMedia('(max-width:700px)')
    const onChange=e=>setCompact(e.matches)
    screen.addEventListener('change',onChange)
    return ()=>screen.removeEventListener('change',onChange)
  },[])
  const camera=useMapCamera(svgRef,focusNode,agents[0]?.task)
  const [entering,setEntering]=useState(false)
  const introduced=useRef(false)
  useEffect(()=>{
    if(!nodes.length){setEntering(false);return}
    if(introduced.current||window.matchMedia('(prefers-reduced-motion: reduce)').matches)return
    introduced.current=true
    setEntering(true)
    const timer=setTimeout(()=>setEntering(false),1800)
    return ()=>clearTimeout(timer)
  },[nodes.length])
  function fit() {
    camera.fit()
    if(selected)onSelect(null)
  }
  function mapKey(e) {
    if(e.ctrlKey||e.metaKey||e.altKey)return
    if(['+', '=', '-', '0','Home'].includes(e.key)){
      e.preventDefault()
      if(e.key==='0'||e.key==='Home')fit()
      else camera.zoomBy(e.key==='-' ? .8 : 1.25)
    }
  }
  return <div className={'swarm-map'+(playing?' moving':'')+(entering?' atlas-entering':'')+(camera.navigating?' navigating':'')} data-testid="swarm-map">
    <svg ref={svgRef} {...camera.pointerProps} onKeyDown={mapKey} focusable="false" className="swarm-diagram" viewBox={compact?"100 0 700 735":"0 0 900 735"}
      aria-label="Investigation swarms and agent handoffs" role="group" aria-describedby="map-control-hint">
      <g className="map-geometry" style={{transform:camera.transform}}>
      <g className="outer-orbits" fill="none"><circle cx="450" cy="365" r="284"/><circle cx="450" cy="365" r="184"/><circle cx="450" cy="365" r="111"/></g>
      {Array.from({length:120},(_,i)=><path key={i} className="degree" d={'M'+point(polar(i*Math.PI/60,279))+'L'+point(polar(i*Math.PI/60,i%5?281:285))}/>)}
      <g className="handoffs">{edges.map(([s,t],i)=>{
        const hot=s.id===selected||t.id===selected, active=preview||status[t.id]==='running'
        const d=curve(s.pos,polar(s.angle,73),polar(t.angle,73),t.pos)
        const id=uid+'-edge-'+i
        return <g key={id}><path id={id} d={d} fill="none" stroke={hot?'#cfc4ac':'#aaa38e'} strokeOpacity={hot ? .86 : selected ? .13 : .44} strokeWidth={hot?1.15:.75}/>
          {playing && active && <circle className="packet" r={hot?3.1:2.55} fill={hot?'#ff9a70':'#f48856'}><animateMotion dur={(2.7+i%5*.49)+'s'} begin={(-i*.71)+'s'} repeatCount="indefinite"><mpath href={'#'+id}/></animateMotion></circle>}
        </g>
      })}</g>
      {Object.keys(GROUPS).map(group=>{
        const v=nodes.filter(n=>n.group===group);if(!v.length)return null
        const start=v[0].angle-v[0].step*.42,end=v.at(-1).angle+v[0].step*.42
        return <g key={group} data-swarm={group}><title>{GROUPS[group]} swarm</title><path d={arc(start,end,277)} fill="none" stroke={C[group]} opacity=".65"/></g>
      })}
      {nodes.map(n=>{
        const focus=n.id===selected, active=status[n.id]==='running'||collectors.has(n.id), color=focus||active?'#ff7849':C[n.group]
        const end=polar(n.angle,299),right=end[0]>=450
        const side=Math.abs(Math.cos(n.angle))>.34
        const x=end[0]+(side?(right?8:-8):0), y=end[1]+(side?0:(end[1]<365?-8:13))
        const textAnchor=side?(right?'start':'end'):'middle'
        return <g key={n.id} role="button" tabIndex="0" aria-pressed={focus} aria-label={n.name+' agent'} data-agent-id={n.id}
          onClick={()=>{if(!camera.draggedRecently())onSelect(n.id)}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(n.id)}}}
          className={'agent-sector'+(focus?' selected':'')} style={{'--sector':color,'--order':n.i,opacity:!selected||focus||edges.some(([a,b])=>(a.id===selected&&b.id===n.id)||(b.id===selected&&a.id===n.id))?1:.36}}>
          <path d={'M'+point(n.pos)+' L'+point(polar(n.angle-n.step*.45,272))+' '+point(polar(n.angle+n.step*.45,272))+'Z'} fill="transparent"/>
          {n.strips.map((v,k)=><g key={k}><path d={v.stem} fill="none" stroke={color} opacity={focus ? .84 : .45} strokeWidth=".8"/>
            {(active || (preview&&k===2)) && playing && <circle r={active?2.6:1.65} fill="#ef976f">
              <animateMotion path={v.stem} keyPoints="1;0" keyTimes="0;1" calcMode="linear" dur={(2.2+k*.4)+'s'} begin={(-n.i*.3-k*.5)+'s'} repeatCount="indefinite"/>
            </circle>}
            <path d={v.path} stroke={color} strokeWidth="1.25" opacity={focus ? 1 : .73}/></g>)}
          <path d={'M'+point(polar(n.angle,279))+'L'+point(end)} stroke={color} opacity=".6" strokeDasharray="2 3"/>
          <circle cx={n.pos[0]} cy={n.pos[1]} r={focus?13:9} fill="#171610" stroke={color}/>
          <circle cx={n.pos[0]} cy={n.pos[1]} r={focus?7:4.5} fill="none" stroke={color}/>
          <circle cx={n.pos[0]} cy={n.pos[1]} r="2" fill={color}/>
          {focus && <path d={arc(n.angle-n.step*.44,n.angle+n.step*.44,275)} fill="none" stroke="#ff845b" strokeWidth="1.6"/>}
          <text x={x} y={y} textAnchor={compact?'middle':textAnchor} className="agent-name">{compact
            ? <><tspan x={x}>{n.name.split(' ')[0]}</tspan><tspan x={x} dy="16">{n.name.split(' ').slice(1).join(' ')}</tspan></>
            : n.name}</text>
          <text x={x} y={y+12} textAnchor={textAnchor} className="agent-sub">{GROUPS[n.group]} swarm{n.report?' · '+n.report.refs.length+' refs':''}</text>
        </g>
      })}
      </g>
    </svg>
    <div className="camera-controls" role="group" aria-label="Map view controls">
      <button type="button" onClick={()=>camera.zoomBy(.8)} aria-label="Zoom out">−</button>
      <button type="button" className="fit-camera" onClick={fit} aria-label="Fit entire map" title="Fit entire map (0)">{Math.round(camera.zoom*100)}%</button>
      <button type="button" onClick={()=>camera.zoomBy(1.25)} aria-label="Zoom in">+</button>
    </div>
    <span id="map-control-hint" className="map-hint">Drag to pan · Scroll or pinch to zoom</span>
    <button type="button" className="motion-control" onClick={onToggle} aria-label={playing?'Pause data flow animation':'Play data flow animation'}>{playing?'Ⅱ':'▷'} <span>{running?'Investigation activity':preview?'Workflow preview':'Case trace'}</span></button>
  </div>
}
