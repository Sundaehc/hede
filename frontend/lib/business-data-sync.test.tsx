import { act, cleanup, render } from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import { publishBusinessDataChange, subscribeBusinessDataChanges } from "@/lib/business-data-sync"
import { useCrossTabRefresh } from "@/lib/use-cross-tab-refresh"

const channels: FakeChannel[] = []
class FakeChannel {
  onmessage: ((event: MessageEvent) => void) | null = null
  postMessage = vi.fn()
  close = vi.fn()
  constructor(public name: string) { channels.push(this) }
}

function remoteNotice(id: string, resources = ["products"]) {
  return { version: 1, id, source: "other-tab", resources }
}

function deliver(id: string, resources?: string[]) {
  channels.at(-1)?.onmessage?.(new MessageEvent("message", { data: remoteNotice(id, resources) }))
}

function Consumer({ refresh, paused = false }: { refresh: () => void; paused?: boolean }) {
  useCrossTabRefresh(["products"], refresh, paused)
  return null
}

beforeEach(() => {
  vi.useFakeTimers()
  channels.length = 0
  window.localStorage.clear()
  vi.stubGlobal("BroadcastChannel", FakeChannel)
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test("shares one listener transport, deduplicates delivery, and never refreshes the saving tab", () => {
  const first = vi.fn()
  const second = vi.fn()
  const unsubscribeFirst = subscribeBusinessDataChanges(first)
  const unsubscribeSecond = subscribeBusinessDataChanges(second)
  expect(channels).toHaveLength(1)
  publishBusinessDataChange(["products"])
  const sent = channels[0].postMessage.mock.calls[0][0]
  expect(sent).toMatchObject({ version: 1, resources: ["products"] })
  expect(Object.keys(sent).sort()).toEqual(["id", "resources", "source", "version"])
  channels[0].onmessage?.(new MessageEvent("message", { data: sent }))
  expect(first).not.toHaveBeenCalled()
  deliver("shared")
  window.dispatchEvent(new StorageEvent("storage", {
    key: "hede:data-change:v1:products", newValue: JSON.stringify(remoteNotice("shared")),
  }))
  expect(first).toHaveBeenCalledTimes(1)
  expect(second).toHaveBeenCalledTimes(1)
  unsubscribeFirst()
  expect(channels[0].close).not.toHaveBeenCalled()
  unsubscribeSecond()
  expect(channels[0].close).toHaveBeenCalledOnce()
})

test("coalesces relevant notices and uses the latest callback without resubscribing", () => {
  const oldRefresh = vi.fn()
  const refresh = vi.fn()
  const view = render(<Consumer refresh={oldRefresh} />)
  act(() => { deliver("batch1"); deliver("batch2"); deliver("unrelated", ["inventory"]) })
  view.rerender(<Consumer refresh={refresh} />)
  act(() => vi.advanceTimersByTime(250))
  expect(oldRefresh).not.toHaveBeenCalled()
  expect(refresh).toHaveBeenCalledOnce()
  expect(channels).toHaveLength(1)
  act(() => { deliver("unrelated2", ["inventory"]); vi.advanceTimersByTime(300) })
  expect(refresh).toHaveBeenCalledOnce()
})

test("defers updates while hidden and refreshes once when returning", () => {
  const visible = vi.spyOn(document, "visibilityState", "get")
  const refresh = vi.fn()
  render(<Consumer refresh={refresh} />)
  visible.mockReturnValue("hidden")
  act(() => { deliver("hidden1"); deliver("hidden2"); vi.advanceTimersByTime(1000) })
  expect(refresh).not.toHaveBeenCalled()
  visible.mockReturnValue("visible")
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"))
    window.dispatchEvent(new Event("focus"))
    vi.advanceTimersByTime(250)
  })
  expect(refresh).toHaveBeenCalledOnce()
  act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(300) })
  expect(refresh).toHaveBeenCalledOnce()
})

test("keeps updates pending through editing and applies them after the editor closes", () => {
  const refresh = vi.fn()
  const view = render(<Consumer refresh={refresh} paused />)
  act(() => { deliver("editing1"); deliver("editing2"); vi.advanceTimersByTime(1000) })
  expect(refresh).not.toHaveBeenCalled()
  view.rerender(<Consumer refresh={refresh} />)
  act(() => vi.advanceTimersByTime(250))
  expect(refresh).toHaveBeenCalledOnce()
})

test("storage fallback handles missed notices on focus and rejects unrelated or invalid values", () => {
  vi.stubGlobal("BroadcastChannel", undefined)
  const refresh = vi.fn()
  render(<Consumer refresh={refresh} />)
  act(() => {
    window.dispatchEvent(new StorageEvent("storage", { key: "other", newValue: JSON.stringify(remoteNotice("ignore")) }))
    window.dispatchEvent(new StorageEvent("storage", { key: "hede:data-change:v1:products", newValue: "invalid" }))
    vi.advanceTimersByTime(300)
  })
  expect(refresh).not.toHaveBeenCalled()
  window.localStorage.setItem("hede:data-change:v1:products", JSON.stringify(remoteNotice("missed")))
  act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(250) })
  expect(refresh).toHaveBeenCalledOnce()
  act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(300) })
  expect(refresh).toHaveBeenCalledOnce()
})

test("notification failures cannot fail a committed save and unmount cancels pending refresh", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked") })
  const refresh = vi.fn()
  const view = render(<Consumer refresh={refresh} />)
  channels[0].postMessage.mockImplementation(() => { throw new Error("closed") })
  expect(() => publishBusinessDataChange(["products"])).not.toThrow()
  act(() => deliver("unmounted"))
  view.unmount()
  act(() => vi.advanceTimersByTime(1000))
  expect(refresh).not.toHaveBeenCalled()
})
