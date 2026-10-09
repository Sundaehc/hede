import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { StrictMode } from "react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { clearSessionScrollPositions, SessionScrollRestoration } from "@/lib/session-scroll-restoration"

const STORAGE_PREFIX = "hede:session-scroll:v1:"
let windowTop = 0
let windowLeft = 0
let documentHeight = 5000
let documentWidth = 1600
let frameNumber = 0
let frames: Map<number, FrameRequestCallback>
let resizeCallbacks: ResizeObserverCallback[]

function flushFrame() {
  act(() => {
    const pending = Array.from(frames.values())
    frames.clear()
    pending.forEach((callback) => callback(0))
  })
}

function flushRestoration() {
  flushFrame()
  flushFrame()
}

function resize() {
  act(() => resizeCallbacks.forEach((callback) => callback([], {} as ResizeObserver)))
  flushRestoration()
}

function remember(pathname: string, top: number, left = 0, containers: Record<string, { top: number; left: number }> = {}, userId = 1) {
  window.sessionStorage.setItem(STORAGE_PREFIX + userId + ":" + pathname, JSON.stringify({ window: { top, left }, containers }))
}

function position(pathname: string, userId = 1) {
  return JSON.parse(window.sessionStorage.getItem(STORAGE_PREFIX + userId + ":" + pathname)!)
}

function scrollWindow(top: number, left = 0) {
  windowTop = top
  windowLeft = left
  fireEvent.scroll(window)
  flushFrame()
}

function Fixture({ pathname = "/inventory", userId = 1, table = false, loading = false }: { pathname?: string; userId?: number; table?: boolean; loading?: boolean }) {
  return <SessionScrollRestoration pathname={pathname} userId={userId}>
    <a href="/products" onClick={(event) => event.preventDefault()}>商品档案</a>
    <div>{loading ? "加载中" : "列表已加载"}</div>
    {table ? <div data-testid="table-scroll" data-scroll-restoration-key="inventory-table" style={{ overflow: "auto" }}>表格</div> : null}
    <div data-testid="dropdown" role="listbox" style={{ overflow: "auto" }}>临时选项</div>
  </SessionScrollRestoration>
}

function tableDimensions(element: HTMLElement, height = 2000, width = 3000) {
  Object.defineProperties(element, {
    scrollHeight: { configurable: true, value: height },
    scrollWidth: { configurable: true, value: width },
    clientHeight: { configurable: true, value: 400 },
    clientWidth: { configurable: true, value: 600 },
  })
}

beforeEach(() => {
  windowTop = 0
  windowLeft = 0
  documentHeight = 5000
  documentWidth = 1600
  frameNumber = 0
  frames = new Map()
  resizeCallbacks = []
  window.history.replaceState(null, "", "/")
  window.history.scrollRestoration = "auto"
  vi.spyOn(window, "scrollY", "get").mockImplementation(() => windowTop)
  vi.spyOn(window, "scrollX", "get").mockImplementation(() => windowLeft)
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(800)
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(1000)
  vi.spyOn(window, "scrollTo").mockImplementation((options: number | ScrollToOptions) => {
    if (typeof options === "object") {
      windowTop = options.top ?? 0
      windowLeft = options.left ?? 0
    }
  })
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockImplementation(() => documentHeight)
  vi.spyOn(document.documentElement, "scrollWidth", "get").mockImplementation(() => documentWidth)
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    frameNumber += 1
    frames.set(frameNumber, callback)
    return frameNumber
  })
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation((frame) => { frames.delete(frame) })
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback: ResizeObserverCallback) { resizeCallbacks.push(callback) }
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
  })
})

afterEach(() => {
  cleanup()
  clearSessionScrollPositions()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test("returns to each page's last scroll position instead of the top", () => {
  const view = render(<Fixture />)
  flushRestoration()
  scrollWindow(1450, 120)
  expect(position("/inventory").window).toEqual({ top: 1450, left: 120 })
  fireEvent.click(screen.getByRole("link"))
  view.rerender(<Fixture pathname="/products" />)
  flushRestoration()
  expect(windowTop).toBe(0)
  scrollWindow(320)
  view.rerender(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(1450)
  expect(windowLeft).toBe(120)
  expect(position("/products").window.top).toBe(320)
})

test("waits for an asynchronous list to become tall enough without losing the saved position", () => {
  remember("/inventory", 2400)
  documentHeight = 950
  const view = render(<Fixture loading />)
  flushRestoration()
  expect(windowTop).toBe(150)
  fireEvent.scroll(window)
  expect(position("/inventory").window.top).toBe(2400)
  documentHeight = 5000
  view.rerender(<Fixture />)
  resize()
  expect(windowTop).toBe(2400)
})

test("restores both directions in independently scrolling tables", () => {
  remember("/inventory", 640, 0, { "key:inventory-table": { top: 700, left: 900 } })
  render(<Fixture table />)
  const table = screen.getByTestId("table-scroll")
  tableDimensions(table)
  resize()
  expect(table.scrollTop).toBe(700)
  expect(table.scrollLeft).toBe(900)
  table.scrollTop = 850
  table.scrollLeft = 1000
  fireEvent.scroll(table)
  flushFrame()
  expect(position("/inventory").containers["key:inventory-table"]).toEqual({ top: 850, left: 1000 })
})

test("restores an asynchronously mounted scroll container", async () => {
  remember("/inventory", 0, 0, { "key:inventory-table": { top: 300, left: 250 } })
  const view = render(<Fixture loading />)
  flushRestoration()
  view.rerender(<Fixture table />)
  const table = screen.getByTestId("table-scroll")
  tableDimensions(table)
  await act(async () => { await Promise.resolve() })
  flushRestoration()
  expect(table.scrollTop).toBe(300)
  expect(table.scrollLeft).toBe(250)
})

test("stops pending restoration when the user manually scrolls", () => {
  remember("/inventory", 2400)
  documentHeight = 950
  render(<Fixture loading />)
  flushRestoration()
  fireEvent.wheel(window)
  scrollWindow(80)
  documentHeight = 5000
  resize()
  expect(windowTop).toBe(80)
  expect(position("/inventory").window.top).toBe(80)
})

test("ignores temporary dropdown scrolling and does not scan the page on every scroll", () => {
  render(<Fixture />)
  flushRestoration()
  const styles = vi.spyOn(window, "getComputedStyle")
  scrollWindow(900)
  const dropdown = screen.getByTestId("dropdown")
  dropdown.scrollTop = 60
  fireEvent.scroll(dropdown)
  flushFrame()
  expect(position("/inventory").containers).toEqual({})
  expect(styles).not.toHaveBeenCalled()
})

test("isolates users while keeping the same page position when returning without an old query string", () => {
  remember("/inventory", 1200, 0, {}, 1)
  const view = render(<Fixture userId={2} />)
  flushRestoration()
  expect(windowTop).toBe(0)
  view.rerender(<Fixture userId={1} />)
  flushRestoration()
  expect(windowTop).toBe(1200)
  window.history.replaceState(null, "", "/inventory?document=other")
  view.unmount()
  render(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(1200)
})

test("logout clears position records without cleanup writing them back", () => {
  const view = render(<Fixture />)
  flushRestoration()
  scrollWindow(900)
  clearSessionScrollPositions()
  view.unmount()
  expect(window.sessionStorage.getItem(STORAGE_PREFIX + "1:/inventory")).toBeNull()
  render(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(0)
})

test("uses an in-memory fallback when session storage is blocked", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage blocked") })
  const view = render(<Fixture />)
  flushRestoration()
  scrollWindow(900)
  view.unmount()
  windowTop = 0
  render(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(900)
})

test("invalid cached values are ignored and server rendering does not access scroll state", () => {
  window.sessionStorage.setItem(STORAGE_PREFIX + "1:/inventory", JSON.stringify({ window: { top: -20, left: 0 }, containers: {} }))
  windowTop = 700
  render(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(0)
  expect(renderToString(<Fixture />)).toContain("列表已加载")
})

test("cancels observers and frame callbacks on leaving the page", () => {
  remember("/inventory", 4000)
  documentHeight = 950
  const view = render(<Fixture loading />)
  view.unmount()
  expect(frames.size).toBe(0)
  expect(window.history.scrollRestoration).toBe("auto")
  expect(position("/inventory").window.top).toBe(4000)
})

test("records the current scroll before navigation even when a frame save is pending", () => {
  const view = render(<Fixture />)
  flushRestoration()
  windowTop = 1100
  fireEvent.scroll(window)
  fireEvent.click(screen.getByRole("link"))
  expect(position("/inventory").window.top).toBe(1100)
  view.rerender(<Fixture pathname="/products" />)
  flushRestoration()
  view.rerender(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(1100)
})

test("persists before reload and retains a manually returned top position", () => {
  const view = render(<Fixture />)
  flushRestoration()
  windowTop = 950
  fireEvent(window, new Event("pagehide"))
  expect(position("/inventory").window.top).toBe(950)
  scrollWindow(0)
  view.unmount()
  windowTop = 950
  render(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(0)
})

test("still restores the saved position under React Strict Mode", () => {
  remember("/inventory", 1800)
  render(<StrictMode><Fixture /></StrictMode>)
  flushRestoration()
  expect(windowTop).toBe(1800)
  scrollWindow(2000)
  expect(position("/inventory").window.top).toBe(2000)
})

test("preserves the last position when an asynchronous page is left before it finishes restoring", () => {
  remember("/inventory", 2800)
  documentHeight = 950
  const view = render(<Fixture loading />)
  flushRestoration()
  view.rerender(<Fixture pathname="/products" />)
  flushRestoration()
  expect(position("/inventory").window.top).toBe(2800)
  documentHeight = 5000
  view.rerender(<Fixture />)
  flushRestoration()
  expect(windowTop).toBe(2800)
})
