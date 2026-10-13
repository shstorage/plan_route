/** Compare JSON content, ignoring indentation; invalid JSON stays unsaved. */
export function projectSignature(text: string): string | null {
  try { return JSON.stringify(JSON.parse(text)) }
  catch { return null }
}

export function hasUnsavedChanges(text: string, saved: string | null, startup: string, nameChanged: boolean, savedFileDeleted = false): boolean {
  const current = projectSignature(text)
  if (nameChanged || savedFileDeleted || current === null) return true
  return saved === null ? current !== startup : current !== saved
}
