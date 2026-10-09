"use client"

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore, type Dispatch, type ReactNode, type SetStateAction } from "react"

const STORAGE_PREFIX = "hede:session-query:v1:"
const SessionQueryScope = createContext("anonymous")
const listeners = new Map<string, Set<() => void>>()
const memoryFallback = new Map<string, string>()
const emptySubscribe = () => () => undefined
const clientReady = () => true
const serverReady = () => false

function storedValue(key: string): string | null {
  if (memoryFallback.has(key)) return memoryFallback.get(key) ?? null
  try {
    return window.sessionStorage.getItem(key)
  } catch {
    return memoryFallback.get(key) ?? null
  }
}

function notify(key: string) {
  listeners.get(key)?.forEach((listener) => listener())
}

function createSessionQueryStore<Value>(storageKey: string, defaultValue: Value) {
  let snapshot: { raw: string | null; value: Value } | null = null
  const getSnapshot = () => {
    const raw = storedValue(storageKey)
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

export function useSessionQueryState<Value>(key: string, initialValue: Value | (() => Value)): [Value, Dispatch<SetStateAction<Value>>] {
  const scope = useContext(SessionQueryScope)
  const storageKey = STORAGE_PREFIX + scope + ":" + key
  const [defaultValue] = useState<Value>(initialValue)
  const { getSnapshot } = useMemo(() => createSessionQueryStore(storageKey, defaultValue), [defaultValue, storageKey])
  const subscribe = useCallback((listener: () => void) => {
    const group = listeners.get(storageKey) ?? new Set<() => void>()
    group.add(listener)
    listeners.set(storageKey, group)
    return () => {
      group.delete(listener)
      if (group.size === 0) listeners.delete(storageKey)
    }
  }, [storageKey])
  const value = useSyncExternalStore(subscribe, getSnapshot, () => defaultValue)
  const setValue = useCallback<Dispatch<SetStateAction<Value>>>((action) => {
    const next = typeof action === "function" ? (action as (current: Value) => Value)(getSnapshot()) : action
    const raw = JSON.stringify(next)
    try {
      window.sessionStorage.setItem(storageKey, raw)
      memoryFallback.delete(storageKey)
    } catch {
      memoryFallback.set(storageKey, raw)
    }
    notify(storageKey)
  }, [getSnapshot, storageKey])
  return [value, setValue]
}
