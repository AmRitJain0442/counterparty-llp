import { useCallback, useEffect, useRef, useState } from 'react'

const clamp = value => Math.max(.65, Math.min(4, value))
const initial = () => ({ x: 0, y: 0, zoom: 1 })

export function useMapCamera(svgRef, focusNode, resetKey) {
  const [camera, setCamera] = useState(initial)
  const current = useRef(camera)
  const pointers = useRef(new Map())
  const lastDrag = useRef(-Infinity)
  const gesture = useRef(false)
  const [navigating, setNavigating] = useState(false)
  const update = useCallback(next => {
    current.current = next
    setCamera(next)
  }, [])
  const point = useCallback((x, y) => {
    const svg = svgRef.current
    const matrix = svg?.getScreenCTM()
    if (!matrix) return null
    const p = svg.createSVGPoint()
    p.x = x
    p.y = y
    return p.matrixTransform(matrix.inverse())
  }, [svgRef])
  const zoomAt = useCallback((factor, p) => {
    if (!Number.isFinite(factor) || factor <= 0 || !p) return
    const c = current.current
    const zoom = clamp(c.zoom * factor)
    const ratio = zoom / c.zoom
    update({ zoom, x: p.x - (p.x - c.x) * ratio, y: p.y - (p.y - c.y) * ratio })
  }, [update])
  const fit = useCallback(() => update(initial()), [update])
  const zoomBy = useCallback(factor => zoomAt(factor, { x: 450, y: 367.5 }), [zoomAt])
  useEffect(() => { fit() }, [resetKey, fit])
  const lastFocus = useRef(null)
  const id = focusNode?.id
  const x = focusNode?.pos?.[0]
  const y = focusNode?.pos?.[1]
  useEffect(() => {
    if (id == null) {
      if (lastFocus.current != null) fit()
      lastFocus.current = null
      return
    }
    if (!Number.isFinite(x) || !Number.isFinite(y)) return
    lastFocus.current = id
    const zoom = 1.65
    update({ zoom, x: 450 - x * zoom, y: 367.5 - y * zoom })
  }, [id, x, y, resetKey, update, fit])
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    let wheelEnd
    const wheel = e => {
      e.preventDefault()
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 735 : 1
      const delta = Math.max(-100, Math.min(100, e.deltaY * unit))
      setNavigating(true)
      zoomAt(Math.exp(-delta * .002), point(e.clientX, e.clientY))
      clearTimeout(wheelEnd)
      wheelEnd = setTimeout(() => { if (!gesture.current) setNavigating(false) }, 100)
    }
    svg.addEventListener('wheel', wheel, { passive: false })
    return () => { svg.removeEventListener('wheel', wheel); clearTimeout(wheelEnd) }
  }, [svgRef, point, zoomAt])
  const end = e => {
    if (!pointers.current.has(e.pointerId)) return
    if (gesture.current) lastDrag.current = Date.now()
    pointers.current.delete(e.pointerId)
    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    if (!pointers.current.size) { gesture.current = false; setNavigating(false) }
  }
  const draggedRecently = useCallback(() => Date.now() - lastDrag.current < 400, [])
  return {
    transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.zoom})`,
    zoom: camera.zoom, zoomBy, fit, draggedRecently, navigating,
    pointerProps: {
      style: { touchAction: 'none' },
      onPointerDown(e) {
        if (e.pointerType === 'mouse' && e.button !== 0) return
        const p = point(e.clientX, e.clientY)
        if (!p) return
        if (!pointers.current.size) lastDrag.current = -Infinity
        pointers.current.set(e.pointerId, { x: p.x, y: p.y, startX: e.clientX, startY: e.clientY })
      },
      onPointerMove(e) {
        const previous = pointers.current.get(e.pointerId)
        if (!previous) return
        const p = point(e.clientX, e.clientY)
        if (!p) return
        if (!gesture.current && Math.hypot(e.clientX - previous.startX, e.clientY - previous.startY) < 4) return
        if (!e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.setPointerCapture(e.pointerId)
        gesture.current = true
        lastDrag.current = Date.now()
        setNavigating(true)
        const other = [...pointers.current.entries()].find(([key]) => key !== e.pointerId)?.[1]
        const c = current.current
        if (other) {
          const before = Math.hypot(previous.x - other.x, previous.y - other.y)
          const after = Math.hypot(p.x - other.x, p.y - other.y)
          const zoom = clamp(c.zoom * (before > 0 ? after / before : 1))
          const ratio = zoom / c.zoom
          update({ zoom, x: (p.x + other.x) / 2 - ((previous.x + other.x) / 2 - c.x) * ratio, y: (p.y + other.y) / 2 - ((previous.y + other.y) / 2 - c.y) * ratio })
        } else update({ ...c, x: c.x + p.x - previous.x, y: c.y + p.y - previous.y })
        pointers.current.set(e.pointerId, { ...previous, x: p.x, y: p.y })
      },
      onPointerUp: end,
      onPointerCancel: end,
      onLostPointerCapture(e) { if (e.target === e.currentTarget) end(e) },
      onClickCapture(e) {
        if (draggedRecently()) { e.preventDefault(); e.stopPropagation() }
      },
    },
  }
}
