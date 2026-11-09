"use client"

import { useEffect, useEffectEvent, useRef } from "react"
import { subscribeBusinessDataChanges, type BusinessDataResource } from "@/lib/business-data-sync"

export function useCrossTabRefresh(
  resources: readonly BusinessDataResource[],
  refresh: () => void,
  paused = false,
) {
  const resourceKey = [...resources].sort().join(",")
  const flushRef = useRef<(() => void) | null>(null)
  const applyRefresh = useEffectEvent(refresh)
  const canRefresh = useEffectEvent(() => !paused && document.visibilityState !== "hidden")

  useEffect(() => {
    let pending = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const flush = () => {
      if (!pending || !canRefresh()) return
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = undefined
        if (!pending || !canRefresh()) return
        pending = false
        applyRefresh()
      }, 250)
    }
    flushRef.current = flush
    const unsubscribe = subscribeBusinessDataChanges((changed) => {
      if (changed.some((resource) => resourceKey.split(",").includes(resource))) pending = true
      flush()
    })
    return () => {
      unsubscribe()
      flushRef.current = null
      if (timer) clearTimeout(timer)
    }
  }, [resourceKey])

  useEffect(() => { if (!paused) flushRef.current?.() }, [paused])
}
