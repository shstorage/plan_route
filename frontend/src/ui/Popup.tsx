import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { fitPopup, resizePopup, type PopupBounds, type ResizeEdge } from './popupGeometry'
import { useHostWindow } from './HostWindow'

/** Native dialogs provide focus restoration and Escape handling for settings. */
export function Popup({ title, children, onClose, companion = false, closeDisabled = false, onDetach }: {
  title: string; children: ReactNode; onClose: () => void; companion?: boolean; closeDisabled?: boolean; onDetach?: () => void
}) {
  const host = useHostWindow()
  const ref = useRef<HTMLDialogElement>(null)
  const drag = useRef<{ pointerId: number; dx: number; dy: number } | null>(null)
  const resize = useRef<{ pointerId: number; x: number; y: number; bounds: PopupBounds; edge: ResizeEdge } | null>(null)
  const restore = useRef<PopupBounds | null>(null)
  const [maximized, setMaximized] = useState(false)
  const titleId = useId()
  const bounds = useCallback((): PopupBounds => {
    const rect = ref.current!.getBoundingClientRect()
    return { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
  }, [])
  const applyBounds = useCallback((next: PopupBounds) => {
    const fitted = fitPopup(next, { width: host.innerWidth, height: host.innerHeight })
    Object.assign(ref.current!.style, {
      left: `${fitted.left}px`, top: `${fitted.top}px`, right: 'auto',
      width: `${fitted.width}px`, height: `${fitted.height}px`,
    })
  }, [host])
  function maximize() {
    if (maximized && restore.current) applyBounds(restore.current)
    else {
      restore.current = bounds()
      applyBounds({ left: 0, top: 0, width: host.innerWidth, height: host.innerHeight })
    }
    setMaximized(!maximized)
  }
  useLayoutEffect(() => {
    const dialog = ref.current!
    if (companion) dialog.show()
    else dialog.showModal()
    dialog.querySelector<HTMLElement>('[data-initial-focus]')?.focus()
    if (companion) applyBounds(bounds())
    return () => dialog.close()
  }, [companion, applyBounds, bounds])
  useEffect(() => {
    if (!companion) return
    const fit = () => {
      if (maximized) applyBounds({ left: 0, top: 0, width: host.innerWidth, height: host.innerHeight })
      else applyBounds(bounds())
    }
    host.addEventListener('resize', fit)
    return () => host.removeEventListener('resize', fit)
  }, [companion, maximized, host, applyBounds, bounds])
  useEffect(() => {
    if (!companion) return
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !host.document.querySelector('dialog:modal')) { ref.current?.close(); onClose() } }
    host.document.addEventListener('keydown', escape)
    return () => host.document.removeEventListener('keydown', escape)
  }, [companion, onClose, host])
  function handle(edge: ResizeEdge, label: string, visible = false) {
    return <button key={edge} type="button" className={visible ? 'popup-resize-handle' : `popup-edge popup-edge-${edge}`} aria-label={label} disabled={maximized}
      title="드래그하거나 방향키로 창 크기를 조절하세요."
      onKeyDown={(event) => {
        const delta = event.shiftKey ? 80 : 20
        const dx = event.key === 'ArrowRight' ? delta : event.key === 'ArrowLeft' ? -delta : 0
        const dy = event.key === 'ArrowDown' ? delta : event.key === 'ArrowUp' ? -delta : 0
        if (!dx && !dy) return
        event.preventDefault(); event.stopPropagation()
        applyBounds(resizePopup(bounds(), edge, dx, dy, { width: host.innerWidth, height: host.innerHeight }))
      }}
      onPointerDown={(event) => {
        if (event.button !== 0) return
        resize.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, bounds: bounds(), edge }
        event.currentTarget.setPointerCapture(event.pointerId)
        event.preventDefault()
      }}
      onPointerMove={(event) => {
        const start = resize.current
        if (!start || start.pointerId !== event.pointerId) return
        applyBounds(resizePopup(start.bounds, start.edge, event.clientX - start.x, event.clientY - start.y, { width: host.innerWidth, height: host.innerHeight }))
      }}
      onPointerUp={() => { resize.current = null }} onPointerCancel={() => { resize.current = null }}>{visible ? '◢' : ''}</button>
  }
  return createPortal(<dialog ref={ref} aria-labelledby={titleId} className={`editor-popup ${companion ? 'companion-popup' : ''}`}
    onCancel={(event) => { event.preventDefault(); if (!closeDisabled) { ref.current?.close(); onClose() } }}>
    <header className="popup-heading" title={companion ? '제목을 드래그해 창을 이동할 수 있습니다.' : undefined}
      onPointerDown={(event) => {
        if (!companion || maximized || event.button !== 0 || (event.target as HTMLElement).closest('button')) return
        const rect = ref.current!.getBoundingClientRect()
        drag.current = { pointerId: event.pointerId, dx: event.clientX - rect.left, dy: event.clientY - rect.top }
        event.currentTarget.setPointerCapture(event.pointerId)
      }}
      onPointerMove={(event) => {
        if (!drag.current || drag.current.pointerId !== event.pointerId) return
        applyBounds({ ...bounds(), left: event.clientX - drag.current.dx, top: event.clientY - drag.current.dy })
      }}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}>
      <h2 id={titleId}>{title}</h2><div className="popup-window-actions">
        {companion && onDetach && <button type="button" className="button-secondary" onClick={onDetach}>새 창으로 열기</button>}
        {companion && <button type="button" className="button-secondary" onClick={maximize} aria-label={`${title} ${maximized ? '원래 크기' : '최대화'}`}>{maximized ? '원래 크기' : '최대화'}</button>}
        <button type="button" className="button-secondary" disabled={closeDisabled} aria-label={`${title} 닫기`} onClick={() => { ref.current?.close(); onClose() }}>닫기 ×</button>
      </div>
    </header>
    <div className={`popup-body${companion ? ' auxiliary-view' : ''}`}>{children}</div>
    {companion && <footer className="popup-resize-bar"><span>테두리·모서리 드래그로 크기 조절 · 다른 모니터는 새 창으로 열기</span>
      {handle('se', `${title} 크기 조절`, true)}
    </footer>}
    {companion && !maximized && (['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'] as const).map((edge) => handle(edge, `${title} ${edge} 테두리 크기 조절`))}
  </dialog>, host.document.body)
}
