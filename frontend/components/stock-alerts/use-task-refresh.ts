"use client"

import { useEffect } from "react"
import { subscribeBusinessDataChanges } from "@/lib/business-data-sync"

// Only small persisted task queries poll; hidden tabs do not issue requests.
export function useTaskRefresh(refresh: () => void) {
  useEffect(() => {
    const unsubscribe = subscribeBusinessDataChanges((resources) => {
      if (
        document.visibilityState !== "hidden" &&
        (!resources.length || resources.includes("stock-alert-tasks"))
      )
        refresh()
    })
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "hidden") refresh()
    }, 60_000)
    return () => {
      unsubscribe()
      window.clearInterval(timer)
    }
  }, [refresh])
}
