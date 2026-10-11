// Undo/redo over serialized EngineeringProject JSON snapshots (domain data only, never Konva state).
export type History = { past: string[]; present: string; future: string[] }

export const HISTORY_LIMIT = 50

export function startHistory(present: string): History {
  return { past: [], present, future: [] }
}

export function pushHistory(history: History, next: string, limit = HISTORY_LIMIT): History {
  if (next === history.present) return history
  return { past: [...history.past, history.present].slice(-limit), present: next, future: [] }
}

export function undoHistory(history: History): History {
  const previous = history.past.at(-1)
  if (previous === undefined) return history
  return { past: history.past.slice(0, -1), present: previous, future: [...history.future, history.present] }
}

export function redoHistory(history: History): History {
  const next = history.future.at(-1)
  if (next === undefined) return history
  return { past: [...history.past, history.present], present: next, future: history.future.slice(0, -1) }
}
