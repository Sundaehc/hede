export type BusinessDataResource = "products" | "inventory" | "reference-data" | "stock-alert-rules"

const RESOURCES: BusinessDataResource[] = ["products", "inventory", "reference-data", "stock-alert-rules"]
const PREFIX = "hede:data-change:v1:"
const CHANNEL = "hede:business-data:v1"
const source = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
  ? crypto.randomUUID()
  : `${Date.now()}-${Math.random()}`
type Notice = { version: 1; id: string; source: string; resources: BusinessDataResource[] }
type Listener = (resources: readonly BusinessDataResource[]) => void
const listeners = new Set<Listener>()
const seen = new Set<string>()
const revisions = new Map<BusinessDataResource, string>()
let channel: BroadcastChannel | null = null

function remember(id: string) {
  seen.add(id)
  if (seen.size > 100) seen.delete(seen.values().next().value!)
}

function receive(value: unknown, notify = true) {
  if (!value || typeof value !== "object") return
  const notice = value as Partial<Notice>
  if (notice.version !== 1 || typeof notice.id !== "string" || typeof notice.source !== "string"
    || !Array.isArray(notice.resources) || !notice.resources.length
    || !notice.resources.every((resource) => RESOURCES.includes(resource))) return
  if (notice.source === source || seen.has(notice.id)) return
  remember(notice.id)
  if (notify) {
    notice.resources.forEach((resource) => revisions.set(resource, notice.id!))
    listeners.forEach((listener) => listener(notice.resources!))
  }
}

// Consumers that retain results across navigation must also detect changes
// made while unmounted, including successful writes from this same tab.
export function getBusinessDataChangeToken(resources: readonly BusinessDataResource[]) {
  return JSON.stringify(resources.map((resource) => {
    let storedId = ""
    try {
      const stored: unknown = JSON.parse(window.localStorage.getItem(PREFIX + resource) ?? "null")
      if (stored && typeof stored === "object" && "id" in stored && typeof stored.id === "string") storedId = stored.id
    } catch { /* The in-memory revision still detects writes when storage is blocked. */ }
    return [resource, revisions.get(resource) ?? "", storedId]
  }))
}

function readStoredNotices(notify: boolean) {
  for (const resource of RESOURCES) {
    try {
      const value = window.localStorage.getItem(PREFIX + resource)
      if (value) receive(JSON.parse(value), notify)
    } catch { /* BroadcastChannel remains usable when browser storage is blocked. */ }
  }
}

function onStorage(event: StorageEvent) {
  if (!event.key || !RESOURCES.some((resource) => event.key === PREFIX + resource) || !event.newValue) return
  try { receive(JSON.parse(event.newValue)) } catch { /* Ignore invalid browser storage. */ }
}

function onForeground() {
  if (document.visibilityState === "hidden") return
  readStoredNotices(true)
  // Flush notices queued while a consumer was hidden, even if already received.
  listeners.forEach((listener) => listener([]))
}

export function subscribeBusinessDataChanges(listener: Listener) {
  if (typeof window === "undefined") return () => undefined
  if (listeners.size === 0) {
    // Initial queries already load current data; do not replay old notices.
    readStoredNotices(false)
    try {
      channel = new BroadcastChannel(CHANNEL)
      channel.onmessage = (event: MessageEvent<unknown>) => receive(event.data)
    } catch { channel = null }
    window.addEventListener("storage", onStorage)
    window.addEventListener("focus", onForeground)
    document.addEventListener("visibilitychange", onForeground)
  }
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (listeners.size > 0) return
    channel?.close()
    channel = null
    window.removeEventListener("storage", onStorage)
    window.removeEventListener("focus", onForeground)
    document.removeEventListener("visibilitychange", onForeground)
  }
}

export function publishBusinessDataChange(resources: BusinessDataResource[]) {
  if (typeof window === "undefined" || !resources.length) return
  const notice: Notice = {
    version: 1, source, id: `${source}:${Date.now()}:${Math.random()}`, resources,
  }
  for (const resource of resources) {
    revisions.set(resource, notice.id)
    try { window.localStorage.setItem(PREFIX + resource, JSON.stringify(notice)) } catch { /* Use the channel below. */ }
  }
  // Do not notify this tab: its save handlers already update the current rows.
  try {
    if (channel) channel.postMessage(notice)
    else {
      const sender = new BroadcastChannel(CHANNEL)
      sender.postMessage(notice)
      sender.close()
    }
  } catch { /* Notifications must never turn a committed save into a failure. */ }
}

export function notifyBusinessMutation(path: string, method = "GET") {
  if (!["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase())) return
  const pathname = path.split("?")[0]
  if (pathname === "/stock-alerts/rules" || pathname === "/stock-alerts/replenishment/rules") {
    publishBusinessDataChange(["stock-alert-rules"])
    return
  }
  if (/^\/products(?:$|\/batch-delete$|\/recycle-bin\/[^/]+\/\d+(?:\/restore)?$|\/[^/]+\/\d+$)/.test(pathname)) {
    publishBusinessDataChange(["products"])
  } else if (/^\/inventory(?:$|\/\d+(?:\/restore|\/details(?:\/\d+|\/batch-delete)?)?$|\/batch-(?:delete|restore|update-costs)$|\/recycle-bin\/batch-delete$|\/import-jst-stock$)/.test(pathname)) {
    publishBusinessDataChange(["inventory"])
  } else if (/^\/(?:size-groups|color-barcodes|product-auxiliary-attributes|supplier-brands|suppliers|warehouse-brands|warehouses)(?:\/|$)/.test(pathname)
    || /^\/inventory\/(?:general-customer-(?:brands|shops|units)|account-subjects)(?:\/|$)/.test(pathname)) {
    publishBusinessDataChange(["reference-data", "products", "inventory"])
  }
}
