import React, { useId, useMemo } from 'react'

const C = {identity:'#d9c7a0', discovery:'#a6c1bd', challenge:'#d6a582', decision:'#c3b5bd'}
export const GROUPS = {identity:'Identity', discovery:'Discovery', challenge:'Challenge', decision:'Decision'}
const polar = (a,r) => [450+Math.cos(a)*r,365+Math.sin(a)*r]
const point = p => p.map(n=>n.toFixed(2)).join(',')
const curve = (a,b,c,d) => 'M'+point(a)+' C'+point(b)+' '+point(c)+' '+point(d)
function arc(a,b,r) {
  return 'M'+point(polar(a,r))+' A'+r+','+r+' 0 0 1 '+point(polar(b,r))
}

function geometry(agents) {
  const sorted = Object.keys(GROUPS).flatMap(g=>agents.filter(a=>a.group===g))
  const step=2*Math.PI/Math.max(sorted.length,1)
  return sorted.map((a,i)=>{
    const angle=-Math.PI/2+step*(i+.45)
    const pos=polar(angle,143)
    const strips=Array.from({length:5},(_,k)=>{
      const t=angle+(k-2)*step*.155
      const w=.048
      const height=31+((i*13+k*17)%49)
      const path=Array.from({length:Math.ceil(height/2.25)},(_,j)=>{
        const r=194+j*2.25
        return 'M'+point(polar(t-w,r))+'L'+point(polar(t+w,r))
      }).join(' ')
      return {path, stem:curve(pos,polar(angle,177),polar(t,168),polar(t,192))}
    })
    return {...a,i,angle,pos,step,strips}
  })
}

export default function SwarmMap({agents,selected,onSelect,events,running,preview,playing,onToggle}) {
  const uid=useId().replace(/[^\w-]/g,'')
  const nodes=useMemo(()=>geometry(agents),[agents])
  const index=Object.fromEntries(nodes.map(n=>[n.id,n]))
  const status=Object.fromEntries(events.filter(e=>e.agent_id).map(e=>[e.agent_id,e.status]))
  const edges=useMemo(()=>{
    const result=[]
    for(const target of nodes) {
      const deps=target.depends_on || []
      for(const dep of deps)if(index[dep])result.push([index[dep],target])
    }
    if(result.length)return result
    const keys=Object.keys(GROUPS)
    for(let i=0;i<keys.length-1;i++){
      const left=nodes.filter(n=>n.group===keys[i]),right=nodes.filter(n=>n.group===keys[i+1])
      left.forEach((n,j)=>right.filter((_,k)=>(j+k)%2===0||right.length===1).forEach(t=>result.push([n,t])))
    }
    return result
  },[nodes])
  return <div className={'swarm-map'+(playing?' moving':'')} data-testid="swarm-map">
    <svg className="swarm-diagram" viewBox="0 0 900 735" aria-label="Investigation swarms and agent handoffs" role="group">
      <g className="outer-orbits" fill="none"><circle cx="450" cy="365" r="284"/><circle cx="450" cy="365" r="184"/><circle cx="450" cy="365" r="111"/></g>
      {Array.from({length:120},(_,i)=><path key={i} className="degree" d={'M'+point(polar(i*Math.PI/60,279))+'L'+point(polar(i*Math.PI/60,i%5?281:285))}/>)}
      <g className="handoffs">{edges.map(([s,t],i)=>{
        const hot=s.id===selected||t.id===selected, active=preview||status[t.id]==='running'
        const d=curve(s.pos,polar(s.angle,73),polar(t.angle,73),t.pos)
        const id=uid+'-edge-'+i
        return <g key={id}><path id={id} d={d} fill="none" stroke={hot?'#cfc4ac':'#aaa38e'} strokeOpacity={hot?.7:.34} strokeWidth={hot?1.15:.75}/>
          {playing && active && <circle className="packet" r={hot?2.8:2} fill={hot?'#ff7547':'#d69d72'}><animateMotion dur={(2.7+i%5*.49)+'s'} begin={(-i*.71)+'s'} repeatCount="indefinite"><mpath href={'#'+id}/></animateMotion></circle>}
        </g>
      })}</g>
      {Object.keys(GROUPS).map(group=>{
        const v=nodes.filter(n=>n.group===group);if(!v.length)return null
        const start=v[0].angle-v[0].step*.42,end=v.at(-1).angle+v[0].step*.42
        return <g key={group} data-swarm={group}><title>{GROUPS[group]} swarm</title><path d={arc(start,end,277)} fill="none" stroke={C[group]} opacity=".65"/></g>
      })}
      {nodes.map(n=>{
        const focus=n.id===selected, active=status[n.id]==='running', color=focus||active?'#ff7849':C[n.group]
        const end=polar(n.angle,299),right=end[0]>=450
        const side=Math.abs(Math.cos(n.angle))>.34
        const x=end[0]+(side?(right?8:-8):0), y=end[1]+(side?0:(end[1]<365?-8:13))
        const textAnchor=side?(right?'start':'end'):'middle'
        return <g key={n.id} role="button" tabIndex="0" aria-pressed={focus} aria-label={n.name+' agent'} data-agent-id={n.id}
          onClick={()=>onSelect(n.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(n.id)}}}
          className={'agent-sector'+(focus?' selected':'')} style={{'--sector':color}}>
          <path d={'M'+point(n.pos)+' L'+point(polar(n.angle-n.step*.45,272))+' '+point(polar(n.angle+n.step*.45,272))+'Z'} fill="transparent"/>
          {n.strips.map((v,k)=><g key={k}><path d={v.stem} fill="none" stroke={color} opacity={focus?.7:.37} strokeWidth=".8"/>
            <path d={v.path} stroke={color} strokeWidth="1.25" opacity={focus?.94:.66}/></g>)}
          <path d={'M'+point(polar(n.angle,279))+'L'+point(end)} stroke={color} opacity=".6" strokeDasharray="2 3"/>
          <circle cx={n.pos[0]} cy={n.pos[1]} r={focus?13:9} fill="#171610" stroke={color}/>
          <circle cx={n.pos[0]} cy={n.pos[1]} r={focus?7:4.5} fill="none" stroke={color}/>
          <circle cx={n.pos[0]} cy={n.pos[1]} r="2" fill={color}/>
          <text x={x} y={y} textAnchor={textAnchor} className="agent-name">{n.name}</text>
          <text x={x} y={y+12} textAnchor={textAnchor} className="agent-sub">{GROUPS[n.group]} swarm</text>
        </g>
      })}
    </svg>
    <button type="button" className="motion-control" onClick={onToggle} aria-label={playing?'Pause data flow animation':'Play data flow animation'}>{playing?'Ⅱ':'▷'} <span>{running?'Live activity':preview?'Workflow preview':'Case trace'}</span></button>
  </div>
}
