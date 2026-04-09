import React, { useEffect, useRef } from 'react'
import { TopBar } from './TopBar'
import { LeftPanel } from './LeftPanel'
import { CenterPanel } from './CenterPanel'
import { RightPanel } from './RightPanel'
import { BottomBar } from './BottomBar'
import { useChatStore, useUIStore } from '../../store'
import { createSession } from '../../api/chat'

export function Shell() {
  const { sessionId, setSession } = useChatStore()
  const { leftPanelWidth, setLeftPanelWidth, bottomPanelHeight, setBottomPanelHeight } = useUIStore()
  const leftStart = useRef({ x: 0, w: 0 })
  const bottomStart = useRef({ y: 0, h: 0 })

  useEffect(() => {
    if (sessionId) return
    const stored = localStorage.getItem('memora_session_id')
    if (stored) {
      setSession(stored)
      return
    }
    createSession()
      .then((res) => {
        const id = res.session_id ?? res.id ?? crypto.randomUUID()
        setSession(id)
        localStorage.setItem('memora_session_id', id)
      })
      .catch(() => {
        const id = crypto.randomUUID()
        setSession(id)
        localStorage.setItem('memora_session_id', id)
      })
  }, [sessionId, setSession])

  function onLeftResizeDown(e: React.PointerEvent) {
    e.preventDefault()
    leftStart.current = { x: e.clientX, w: leftPanelWidth }
    const onMove = (ev: PointerEvent) => {
      setLeftPanelWidth(leftStart.current.w + ev.clientX - leftStart.current.x)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  function onBottomResizeDown(e: React.PointerEvent) {
    e.preventDefault()
    bottomStart.current = { y: e.clientY, h: bottomPanelHeight }
    const onMove = (ev: PointerEvent) => {
      const delta = ev.clientY - bottomStart.current.y
      setBottomPanelHeight(bottomStart.current.h - delta)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'
  }

  return (
    <div className="shell">
      <TopBar />
      <div className="shell-main-row">
        <div className="shell-left" style={{ width: leftPanelWidth }}>
          <LeftPanel />
        </div>
        <button
          type="button"
          className="shell-resize-v"
          aria-label="Resize memory stream panel"
          onPointerDown={onLeftResizeDown}
        />
        <div className="shell-center">
          <CenterPanel />
        </div>
        <div className="shell-right">
          <RightPanel />
        </div>
      </div>
      <button
        type="button"
        className="shell-resize-h"
        aria-label="Resize knowledge graph panel height"
        onPointerDown={onBottomResizeDown}
      />
      <BottomBar />
    </div>
  )
}
