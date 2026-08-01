import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { PageContextEnvelope } from '../api/client'

type ContextPatch = Partial<
  Omit<PageContextEnvelope, 'contextVersion' | 'capturedAt' | 'pageViewId' | 'correlationId'>
>

export type OperatorContextValue = {
  context: PageContextEnvelope
  captureContext: () => PageContextEnvelope
  registerContextPatch: (key: string, patch: ContextPatch | null) => () => void
}

const OperatorContext = createContext<OperatorContextValue | null>(null)

function randomId(prefix: string) {
  const generated =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
  return `${prefix}-${generated}`
}

export function OperatorContextProvider({
  baseContext,
  children,
}: {
  baseContext: PageContextEnvelope
  children: ReactNode
}) {
  const [patches, setPatches] = useState<Record<string, ContextPatch>>({})
  const versionRef = useRef(baseContext.contextVersion)

  useEffect(() => {
    versionRef.current += 1
  }, [baseContext.pathname, baseContext.routeId, baseContext.projectId])

  const context = useMemo<PageContextEnvelope>(() => {
    const mergedPatch = Object.values(patches).reduce<ContextPatch>(
      (acc, patch) => ({ ...acc, ...patch }),
      {},
    )
    return {
      ...baseContext,
      ...mergedPatch,
      contextVersion: versionRef.current,
      capabilities: Array.from(
        new Set([...(baseContext.capabilities ?? []), ...(mergedPatch.capabilities ?? [])]),
      ),
    }
  }, [baseContext, patches])

  const captureContext = useCallback((): PageContextEnvelope => {
    versionRef.current += 1
    return {
      ...context,
      contextVersion: versionRef.current,
      capturedAt: new Date().toISOString(),
      correlationId: randomId('operator-correlation'),
    }
  }, [context])

  const registerContextPatch = useCallback((key: string, patch: ContextPatch | null) => {
    setPatches((current) => {
      const next = { ...current }
      if (patch) next[key] = patch
      else delete next[key]
      return next
    })
    return () => {
      setPatches((current) => {
        if (!(key in current)) return current
        const next = { ...current }
        delete next[key]
        return next
      })
    }
  }, [])

  const value = useMemo(
    () => ({ context, captureContext, registerContextPatch }),
    [captureContext, context, registerContextPatch],
  )

  return <OperatorContext.Provider value={value}>{children}</OperatorContext.Provider>
}

export function useOperatorContext(): OperatorContextValue {
  const value = useContext(OperatorContext)
  if (!value) {
    throw new Error('useOperatorContext must be used inside OperatorContextProvider')
  }
  return value
}

export function useOptionalOperatorContext(): OperatorContextValue | null {
  return useContext(OperatorContext)
}

export function useRegisterOperatorContext(key: string, patch: ContextPatch | null) {
  const { registerContextPatch } = useOperatorContext()
  useEffect(() => registerContextPatch(key, patch), [key, patch, registerContextPatch])
}
