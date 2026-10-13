export type PopupBounds = { left: number; top: number; width: number; height: number }
export type Viewport = { width: number; height: number }
export type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

/** Keep the heading and resize handle reachable even on a small viewport. */
export function fitPopup(bounds: PopupBounds, viewport: Viewport): PopupBounds {
  const margin = 0
  const maxWidth = Math.max(1, viewport.width - margin * 2)
  const maxHeight = Math.max(1, viewport.height - margin * 2)
  const width = Math.max(Math.min(480, maxWidth), Math.min(bounds.width, maxWidth))
  const height = Math.max(Math.min(320, maxHeight), Math.min(bounds.height, maxHeight))
  return {
    width, height,
    left: Math.max(margin, Math.min(bounds.left, viewport.width - width - margin)),
    top: Math.max(margin, Math.min(bounds.top, viewport.height - height - margin)),
  }
}

/** Drag an edge while anchoring its opposite edge, including at minimum size. */
export function resizePopup(start: PopupBounds, edge: ResizeEdge, dx: number, dy: number, viewport: Viewport): PopupBounds {
  const minWidth = Math.min(480, viewport.width)
  const minHeight = Math.min(320, viewport.height)
  let left = start.left, top = start.top
  let right = left + start.width, bottom = top + start.height
  if (edge.includes('w')) left = Math.max(0, Math.min(left + dx, right - minWidth))
  if (edge.includes('e')) right = Math.min(viewport.width, Math.max(right + dx, left + minWidth))
  if (edge.includes('n')) top = Math.max(0, Math.min(top + dy, bottom - minHeight))
  if (edge.includes('s')) bottom = Math.min(viewport.height, Math.max(bottom + dy, top + minHeight))
  return { left, top, width: right - left, height: bottom - top }
}
