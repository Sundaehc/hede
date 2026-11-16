import type { BusinessDataResource } from "./business-data-sync"

const MAX_ENTRIES = 32
const MAX_BYTES = 4 * 1024 * 1024
type Entry = {
  data: unknown
  expires: number
  retainUntil: number
  bytes: number
  family: string
  factsToken?: string
}
type Pending = {
  promise: Promise<unknown>
  controller: AbortController
  consumers: Set<symbol>
  family: string
}
const entries = new Map<string, Entry>()
const pending = new Map<string, Pending>()

export const STOCK_SOURCE_RESOURCES: readonly BusinessDataResource[] = [
  "products",
  "inventory",
  "reference-data",
]
export const STOCK_FACT_RESOURCES: readonly BusinessDataResource[] = [
  ...STOCK_SOURCE_RESOURCES,
  "stock-alert-rules",
]
export const STOCK_ALERT_RESOURCES: readonly BusinessDataResource[] = [
  ...STOCK_FACT_RESOURCES,
  "stock-alert-tasks",
]
export const STOCK_TASK_RESOURCES: readonly BusinessDataResource[] = [
  "stock-alert-tasks",
]

export function stockModuleFactsChanged(
  family: string,
  token: string | undefined
) {
  let previous: Entry | undefined
  for (const item of entries.values())
    if (item.family === family) previous = item
  return (
    token !== undefined &&
    previous?.factsToken !== undefined &&
    previous.factsToken !== token
  )
}

export function clearStockModuleQueries() {
  entries.clear()
  for (const item of pending.values()) item.controller.abort()
  pending.clear()
}

export function invalidateStockModuleFamily(family: string) {
  for (const [key, item] of entries)
    if (item.family === family) entries.delete(key)
  // A response started before a refresh may finish, but cannot repopulate the cache.
  for (const [key, item] of pending)
    if (item.family === family) pending.delete(key)
}

export function readStockModuleQuery<T>(key: string) {
  const item = entries.get(key)
  return item && item.retainUntil > Date.now()
    ? { ...item, fresh: item.expires > Date.now(), data: item.data as T }
    : null
}

export function loadStockModuleQuery<T>(
  key: string,
  family: string,
  load: (signal: AbortSignal) => Promise<T>,
  signal: AbortSignal,
  ttl: number,
  retention: number,
  factsToken?: string
): Promise<T> {
  if (signal.aborted)
    return Promise.reject(new DOMException("Aborted", "AbortError"))
  const cached = readStockModuleQuery<T>(key)
  if (cached && cached.expires > Date.now()) return Promise.resolve(cached.data)
  let item = pending.get(key)
  if (!item || item.controller.signal.aborted) {
    const controller = new AbortController()
    item = {
      controller,
      consumers: new Set(),
      family,
      promise: Promise.resolve(),
    }
    const current = item
    // Defer the loader until consumers attach; also shares Strict Mode remounts.
    item.promise = Promise.resolve()
      .then(() => load(controller.signal))
      .then((data) => {
        if (!controller.signal.aborted && pending.get(key) === current) {
          const bytes = JSON.stringify(data).length * 2
          entries.delete(key)
          for (const [oldKey, entry] of entries)
            if (entry.retainUntil <= Date.now()) entries.delete(oldKey)
          if (bytes <= MAX_BYTES)
            entries.set(key, {
              data,
              bytes,
              family,
              factsToken,
              expires: Date.now() + ttl,
              retainUntil: Date.now() + retention,
            })
          let total = [...entries.values()].reduce(
            (sum, entry) => sum + entry.bytes,
            0
          )
          while (entries.size > MAX_ENTRIES || total > MAX_BYTES) {
            const oldest = entries.keys().next().value!
            total -= entries.get(oldest)!.bytes
            entries.delete(oldest)
          }
        }
        return data
      })
      .finally(() => {
        if (pending.get(key) === current) pending.delete(key)
      })
    pending.set(key, item)
  }
  const current = item
  const consumer = Symbol()
  current.consumers.add(consumer)
  return new Promise<T>((resolve, reject) => {
    const detach = () => {
      signal.removeEventListener("abort", abort)
      current.consumers.delete(consumer)
    }
    const abort = () => {
      detach()
      reject(new DOMException("Aborted", "AbortError"))
      queueMicrotask(() => {
        if (!current.consumers.size) current.controller.abort()
      })
    }
    signal.addEventListener("abort", abort, { once: true })
    current.promise.then(
      (data) => {
        detach()
        resolve(data as T)
      },
      (error: unknown) => {
        detach()
        reject(error)
      }
    )
  })
}
