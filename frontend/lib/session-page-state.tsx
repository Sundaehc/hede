"use client"

import { useSyncExternalStore, type ReactNode } from "react"

import { clearSessionQueryStates } from "@/lib/session-query-state"
import { clearSessionScrollPositions } from "@/lib/session-scroll-restoration"

let initialized = false

export function initializeSessionPageState() {
  if (initialized || typeof window === "undefined") return
  initialized = true
  try {
    const navigation = window.performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined
    if (navigation?.type !== "reload") return
  } catch {
    return
  }
  clearSessionQueryStates()
  clearSessionScrollPositions()
  window.history.scrollRestoration = "manual"
}

function subscribe(listener: () => void) {
  initializeSessionPageState()
  listener()
  return () => undefined
}

const clientReady = () => initialized
const serverReady = () => false

export function SessionPageStateBoundary({ children }: { children: ReactNode }) {
  const ready = useSyncExternalStore(subscribe, clientReady, serverReady)
  return ready ? children : null
}
