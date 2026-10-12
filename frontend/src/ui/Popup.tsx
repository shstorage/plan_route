import { useEffect, useId, useLayoutEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Native dialogs provide focus restoration and Escape handling for settings. */
export function Popup({ title, children, onClose, companion = false }: {
  title: string; children: ReactNode; onClose: () => void; companion?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const drag = useRef<{ pointerId: number; dx: number; dy: number } | null>(null)
  const titleId = useId()
  useLayoutEffect(() => {
    const dialog = ref.current!
    if (companion) dialog.show()
    else dialog.showModal()
    return () => dialog.close()
  }, [companion])
  useEffect(() => {
    if (!companion) return
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { ref.current?.close(); onClose() } }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [companion, onClose])
  return createPortal(<dialog ref={ref} aria-labelledby={titleId} className={`editor-popup ${companion ? 'companion-popup' : ''}`}
    onCancel={(event) => { event.preventDefault(); ref.current?.close(); onClose() }}>
    <header className="popup-heading" title={companion ? '제목을 드래그해 창을 이동할 수 있습니다.' : undefined}
      onPointerDown={(event) => {
        if (!companion || event.button !== 0 || (event.target as HTMLElement).closest('button')) return
        const rect = ref.current!.getBoundingClientRect()
        drag.current = { pointerId: event.pointerId, dx: event.clientX - rect.left, dy: event.clientY - rect.top }
        event.currentTarget.setPointerCapture(event.pointerId)
      }}
      onPointerMove={(event) => {
        if (!drag.current || drag.current.pointerId !== event.pointerId) return
        const dialog = ref.current!
        const rect = dialog.getBoundingClientRect()
        dialog.style.left = `${Math.max(0, Math.min(window.innerWidth - rect.width, event.clientX - drag.current.dx))}px`
        dialog.style.top = `${Math.max(0, Math.min(window.innerHeight - 50, event.clientY - drag.current.dy))}px`
        dialog.style.right = 'auto'
      }}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}>
      <h2 id={titleId}>{title}</h2><button type="button" className="button-secondary" aria-label={`${title} 닫기`} onClick={() => { ref.current?.close(); onClose() }}>닫기 ×</button>
    </header>
    <div className="popup-body">{children}</div>
  </dialog>, document.body)
}
