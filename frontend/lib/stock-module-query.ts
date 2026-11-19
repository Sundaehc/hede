"use client"

import { useEffect, useEffectEvent, useRef, useState } from "react"
import { useAuth } from "@/components/auth/auth-provider"
import {
  getBusinessDataChangeToken,
  type BusinessDataResource,
} from "./business-data-sync"
import {
  invalidateStockModuleFamily,
  loadStockModuleQuery,
  readStockModuleQuery,
  stockModuleFactsChanged,
} from "./stock-module-cache"
export {
  clearStockModuleQueries,
  STOCK_SOURCE_RESOURCES,
  STOCK_FACT_RESOURCES,
  STOCK_ALERT_RESOURCES,
  STOCK_TASK_RESOURCES,
} from "./stock-module-cache"

const OPTION_RESOURCES: readonly BusinessDataResource[] = ["reference-data"]

export function useStockModuleQuery<T>({
  group,
  queryKey,
  previousDataKey,
  revision = 0,
  resources,
  load,
  ttl = 30_000,
  retention = 120_000,
  factResources,
}: {
  group: string
  queryKey: string
  /** Only reuse previous results from this display scope, when provided. */
  previousDataKey?: string
  revision?: number
  resources: readonly BusinessDataResource[]
  load: (signal: AbortSignal, refreshFacts: boolean) => Promise<T>
  ttl?: number
  retention?: number
  factResources?: readonly BusinessDataResource[]
}) {
  const { user } = useAuth()
  const scope = JSON.stringify([
    user?.id ?? "anonymous",
    user?.permissions ?? [],
  ])
  const family = JSON.stringify([scope, group])
  const [businessDay] = useState(() =>
    new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10)
  )
  const key = JSON.stringify([
    family,
    queryKey,
    businessDay,
    getBusinessDataChangeToken(resources),
  ])
  const factsToken = factResources
    ? getBusinessDataChangeToken(factResources)
    : undefined
  const [state, setState] = useState<{
    key: string
    family: string
    previousDataKey?: string
    revision: number
    data: T | null
    error: string | null
  } | null>(null)
  const lastRevision = useRef(revision)
  const loadLatest = useEffectEvent(load)
  const cached = readStockModuleQuery<T>(key)
  const current = state?.key === key ? state : null
  const data = current?.data ?? cached?.data ?? null
  const error = current?.revision === revision ? current.error : null
  const loading = data === null && !error
  const refreshing =
    current?.revision !== revision && (revision > 0 || !cached?.fresh)

  useEffect(() => {
    const controller = new AbortController()
    const refreshFacts = stockModuleFactsChanged(family, factsToken)
    if (lastRevision.current !== revision || refreshFacts)
      invalidateStockModuleFamily(family)
    lastRevision.current = revision
    loadStockModuleQuery(
      key,
      family,
      (signal) => loadLatest(signal, refreshFacts),
      controller.signal,
      ttl,
      retention,
      factsToken
    )
      .then((data) => {
        if (!controller.signal.aborted)
          setState({
            key,
            family,
            previousDataKey,
            revision,
            data,
            error: null,
          })
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setState((previous) => ({
            key,
            family,
            previousDataKey,
            revision,
            data:
              previous?.key === key
                ? previous.data
                : (readStockModuleQuery<T>(key)?.data ?? null),
            error: cause instanceof Error ? cause.message : "加载失败，请重试",
          }))
      })
    return () => controller.abort()
  }, [key, family, previousDataKey, revision, ttl, retention, factsToken])

  return {
    data,
    previousData:
      state?.family === family &&
      (previousDataKey === undefined ||
        state.previousDataKey === previousDataKey)
        ? state.data
        : null,
    error,
    loading,
    refreshing: loading || refreshing,
  }
}

export function useStockModuleOptions(
  load: (
    signal: AbortSignal
  ) => Promise<{ brands: Array<{ value: string; label: string }> }>
) {
  return useStockModuleQuery({
    group: "stock-options",
    queryKey: "brands",
    resources: OPTION_RESOURCES,
    load,
    ttl: 300_000,
    retention: 300_000,
  })
}
