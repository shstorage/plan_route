export type CompanionView = '2d' | '3d'
export type DetachedTarget = { window: Window; container: HTMLDivElement }

/** Called directly from a click so browser popup policies can allow the window. */
export function openDetachedWindow(): DetachedTarget | null {
  const width = Math.min(960, window.screen.availWidth || 960)
  const height = Math.min(900, window.screen.availHeight || 900)
  const child = window.open('', '_blank', `popup,width=${width},height=${height},resizable=yes,scrollbars=yes`)
  if (!child) return null
  child.document.documentElement.lang = 'ko'
  const viewport = child.document.createElement('meta')
  viewport.name = 'viewport'
  viewport.content = 'width=device-width, initial-scale=1'
  child.document.head.append(viewport)
  child.document.body.className = 'external-companion'
  const container = child.document.createElement('div')
  container.className = 'external-companion-root'
  child.document.body.append(container)
  return { window: child, container }
}
