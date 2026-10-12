import type { KeyboardEvent } from 'react'

export function onTabKeyDown(event: KeyboardEvent<HTMLDivElement>) {
  const tabs = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
  const current = tabs.indexOf(document.activeElement as HTMLButtonElement)
  const next = event.key === 'ArrowRight' ? (current + 1) % tabs.length
    : event.key === 'ArrowLeft' ? (current + tabs.length - 1) % tabs.length
    : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1
  if (next >= 0 && !event.altKey && !event.ctrlKey && !event.metaKey) {
    event.preventDefault()
    tabs[next].focus()
    tabs[next].click()
  }
}
