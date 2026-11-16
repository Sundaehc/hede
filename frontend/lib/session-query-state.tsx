"use client"

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore, type Dispatch, type ReactNode, type SetStateAction } from "react"

const STORAGE_PREFIX = "hede:session-query:v1:"
const PREFERENCE_STORAGE_PREFIX = "hede:account-preference:v1:"
type StorageKind = "session" | "local"
const SessionQueryScope = createContext("anonymous")
const listeners = new Map<string, Set<() => void>>()
const memoryFallback = new Map<string, string>()
const preferenceFallback = new Map<string, string>()
const emptySubscribe = () => () => undefined
const clientReady = () => true
const serverReady = () => false

function storedValue(key: string, kind: StorageKind): string | null {
  const fallback = kind === "local" ? preferenceFallback : memoryFallback
  if (fallback.has(key)) return fallback.get(key) ?? null
  try {
    return (kind === "local" ? window.localStorage : window.sessionStorage).getItem(key)
  } catch {
    return fallback.get(key) ?? null
  }
}

function notify(key: string) {
  listeners.get(key)?.forEach((listener) => listener())
}

function createBrowserStateStore<Value>(storageKey: string, defaultValue: Value, kind: StorageKind) {
  let snapshot: { raw: string | null; value: Value } | null = null
  const getSnapshot = () => {
    const raw = storedValue(storageKey, kind)
    if (snapshot?.raw === raw) return snapshot.value
    let value = defaultValue
    if (raw !== null) {
      try {
        const parsed = JSON.parse(raw)
        if (defaultValue === null || (Array.isArray(defaultValue) ? Array.isArray(parsed) : typeof parsed === typeof defaultValue && parsed !== null && !Array.isArray(parsed))) {
          value = parsed as Value
        }
      } catch {
        value = defaultValue
      }
    }
    snapshot = { raw, value }
    return value
  }
  return { getSnapshot }
}

export function clearSessionQueryStates() {
  try {
    const keys = Object.keys(window.sessionStorage).filter((key) => key.startsWith(STORAGE_PREFIX))
    keys.forEach((key) => window.sessionStorage.removeItem(key))
  } catch {
    memoryFallback.clear()
  }
  memoryFallback.clear()
  listeners.forEach((_, key) => notify(key))
}

export function SessionQueryProvider({ userId, children }: { userId: number | null; children: ReactNode }) {
  const ready = useSyncExternalStore(emptySubscribe, clientReady, serverReady)
  return <SessionQueryScope.Provider value={userId === null ? "anonymous" : String(userId)}>{ready ? children : null}</SessionQueryScope.Provider>
}

function useBrowserState<Value>(key: string, initialValue: Value | (() => Value), kind: StorageKind): [Value, Dispatch<SetStateAction<Value>>] {
  const scope = useContext(SessionQueryScope)
  const storageKey = (kind === "local" ? PREFERENCE_STORAGE_PREFIX : STORAGE_PREFIX) + scope + ":" + key
  const [defaultValue] = useState<Value>(initialValue)
  const { getSnapshot } = useMemo(() => createBrowserStateStore(storageKey, defaultValue, kind), [defaultValue, storageKey, kind])
  const subscribe = useCallback((listener: () => void) => {
    const group = listeners.get(storageKey) ?? new Set<() => void>()
    group.add(listener)
    listeners.set(storageKey, group)
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) listener()
    }
    if (kind === "local") window.addEventListener("storage", onStorage)
    return () => {
      group.delete(listener)
      if (group.size === 0) listeners.delete(storageKey)
      if (kind === "local") window.removeEventListener("storage", onStorage)
    }
  }, [storageKey, kind])
  const value = useSyncExternalStore(subscribe, getSnapshot, () => defaultValue)
  const setValue = useCallback<Dispatch<SetStateAction<Value>>>((action) => {
    const next = typeof action === "function" ? (action as (current: Value) => Value)(getSnapshot()) : action
    const raw = JSON.stringify(next)
    const fallback = kind === "local" ? preferenceFallback : memoryFallback
    try {
      (kind === "local" ? window.localStorage : window.sessionStorage).setItem(storageKey, raw)
      fallback.delete(storageKey)
    } catch {
      fallback.set(storageKey, raw)
    }
    notify(storageKey)
  }, [getSnapshot, storageKey, kind])
  return [value, setValue]
}

export function useSessionQueryState<Value>(key: string, initialValue: Value | (() => Value)): [Value, Dispatch<SetStateAction<Value>>] {
  return useBrowserState(key, initialValue, "session")
}

// Layout preferences survive reload and logout, with a separate key per account.
export function useAccountPreferenceState<Value>(key: string, initialValue: Value | (() => Value)): [Value, Dispatch<SetStateAction<Value>>] {
  return useBrowserState(key, initialValue, "local")
}
