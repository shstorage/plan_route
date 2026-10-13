const paths = {
  select: 'M5 3v16l4-5 4 7 3-2-4-6 6-1Z',
  equipment: 'M5 7h14v13H5ZM7 7V3h10v4M2 11h3m14 0h3M8 16h8',
  wall: 'M3 5h18v14H3ZM3 12h18M9 5v7m6 0v7',
  zone: 'M3 3h18v18H3ZM8 8h8v8H8Z',
  connect: 'M5 5h6v14h8m-4-4 4 4-4 4M5 2v6',
  companion: 'M3 4h18v16H3ZM14 4v16',
  external: 'M14 3h7v7m0-7-9 9M10 5H3v16h16v-7',
} as const
export function ToolIcon({ kind }: { kind: keyof typeof paths }) {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind]} /></svg>
}
