import { createContext, useContext } from 'react'

/** Portalled controls use their actual document for keys, dialogs and cursors. */
export const HostWindowContext = createContext<Window | null>(null)
export function useHostWindow(): Window { return useContext(HostWindowContext) ?? window }
