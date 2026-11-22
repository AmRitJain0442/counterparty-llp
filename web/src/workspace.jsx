import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import DiscussionRoom from './DiscussionRoom'
import ProviderRoom from './ProviderRoom'
import LiveWorkbench from './LiveWorkbench'
import './workbench.css'
import './workspace.css'

const views = {
  flow: ['Discussion room', DiscussionRoom],
  live: ['Live investigation', LiveWorkbench],
  providers: ['Provider room', ProviderRoom],
}
function Workspace() {
  const getTab=()=>Object.hasOwn(views,location.hash.slice(1))?location.hash.slice(1):'flow'
  const [tab,setTab]=useState(getTab)
  React.useEffect(()=>{
    const change=()=>setTab(getTab())
    window.addEventListener('hashchange',change)
    return ()=>window.removeEventListener('hashchange',change)
  },[])
  const View=views[tab][1]
  return <><header className="room-nav"><a href="/" className="room-brand"><img src="/brand/mark.svg" alt=""/>Counterparty <em>LLP</em></a>
    <nav aria-label="Workspace">{Object.entries(views).map(([id,[label]])=><a key={id} href={'#'+id} aria-current={tab===id?'page':undefined}>{label}</a>)}</nav>
    <a className="return-desk" href="/">Desk map ↗</a></header>
    <main><View/></main></>
}
createRoot(document.getElementById('root')).render(<Workspace/>)
