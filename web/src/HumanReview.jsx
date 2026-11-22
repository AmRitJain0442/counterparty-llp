import React, {useEffect, useState} from 'react'

export default function HumanReview({caseId}) {
  const [items,setItems]=useState([])
  const [note,setNote]=useState('')
  const [disposition,setDisposition]=useState('Callback requested')
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)
  const url='/api/cases/'+encodeURIComponent(caseId)+'/reviews'
  useEffect(()=>{
    const c=new AbortController()
    setNote('');setItems([]);setMessage('')
    fetch(url,{signal:c.signal}).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setItems)
      .catch(e=>{if(e.name!=='AbortError')setMessage('Review log unavailable.')})
    return ()=>c.abort()
  },[url])
  async function record(e) {
    e.preventDefault();setBusy(true);setMessage('')
    try {
      const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({disposition,note})})
      if(!r.ok)throw new Error()
      const row=await r.json()
      setItems(previous=>[...previous,row]);setNote('');setMessage('Review recorded.')
    }catch{setMessage('Review could not be saved.')}
    finally{setBusy(false)}
  }
  return <section className="human-review"><h2>Human review</h2>
    {items.map(row=><article key={row.id}><strong>{row.disposition}</strong> · {new Date(row.as_of).toLocaleString()}<p>{row.note}</p></article>)}
    <form onSubmit={record}><label>Disposition<select value={disposition} onChange={e=>setDisposition(e.target.value)}>
      {['Callback requested','Clarification requested','Evidence corrected','Review complete'].map(v=><option key={v}>{v}</option>)}
    </select></label>
    <label>Review note<textarea maxLength={800} required value={note} onChange={e=>setNote(e.target.value)} /></label>
    <button disabled={busy || !note.trim()}>Record review</button><p role="status">{message}</p></form>
  </section>
}
