import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { EntryMode } from '../scenario/types'

interface OperationsState {
  readonly mode: EntryMode
  readonly referenceTime: string | null
  readonly selectedSubstationId: number
  readonly selectAsset: (substationId: number) => void
}

const OperationsContext = createContext<OperationsState | null>(null)

export function OperationsProvider({ children, mode, referenceTime, initialSubstationId }: {
  readonly children: ReactNode
  readonly mode: EntryMode
  readonly referenceTime: string | null
  readonly initialSubstationId: number
}) {
  const [selectedSubstationId, setSelectedSubstationId] = useState(initialSubstationId)
  useEffect(() => setSelectedSubstationId(initialSubstationId), [initialSubstationId])
  const value = useMemo<OperationsState>(() => ({
    mode,
    referenceTime,
    selectedSubstationId,
    selectAsset: setSelectedSubstationId,
  }), [mode, referenceTime, selectedSubstationId])
  return <OperationsContext.Provider value={value}>{children}</OperationsContext.Provider>
}

export function useOperations(): OperationsState {
  const value = useContext(OperationsContext)
  if (value == null) throw new Error('OperationsProvider is required')
  return value
}
