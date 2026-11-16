import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { StrictMode } from "react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { clearSessionQueryStates, SessionQueryProvider, useAccountPreferenceState, useSessionQueryState } from "@/lib/session-query-state"
import { clearSessionScrollPositions } from "@/lib/session-scroll-restoration"

const QUERY_KEY = "hede:session-query:v1:1:inventory:query"
const PAGE_KEY = "hede:session-query:v1:1:inventory:page"
const SCROLL_KEY = "hede:session-scroll:v1:1:/inventory"

function remember() {
  window.sessionStorage.setItem(QUERY_KEY, JSON.stringify("已保存筛选"))
  window.sessionStorage.setItem(PAGE_KEY, JSON.stringify(5))
  window.sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ window: { top: 1800, left: 0 }, containers: { "key:inventory-table": { top: 700, left: 900 } } }))
  window.sessionStorage.setItem("theme", "dark")
  window.sessionStorage.setItem("unrelated", "keep")
}

function QueryFixture() {
  const [query, setQuery] = useSessionQueryState("inventory:query", "")
  const [page] = useSessionQueryState("inventory:page", 1)
  return <div>
    <input aria-label="筛选" value={query} onChange={(event) => setQuery(event.target.value)} />
    <output aria-label="页码">{page}</output>
  </div>
}

function LayoutPreferenceFixture() {
  const [order] = useAccountPreferenceState<string[]>("purchase-order:detail-columns:v1", ["product_code", "amount"])
  return <output aria-label="明细字段顺序">{order.join(",")}</output>
}

beforeEach(() => {
  vi.resetModules()
  remember()
})

afterEach(() => {
  cleanup()
  clearSessionQueryStates()
  clearSessionScrollPositions()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function navigationType(type: string) {
  const getEntriesByType = vi.fn().mockReturnValue([{ type }])
  Object.defineProperty(window.performance, "getEntriesByType", { configurable: true, value: getEntriesByType })
  return getEntriesByType
}

test("browser reload clears saved filters, pagination and both scroll directions before mounting the page", async () => {
  navigationType("reload")
  const { SessionPageStateBoundary } = await import("@/lib/session-page-state")
  render(<SessionPageStateBoundary><SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider></SessionPageStateBoundary>)
  expect(screen.getByLabelText("筛选")).toHaveValue("")
  expect(screen.getByLabelText("页码")).toHaveTextContent("1")
  expect(window.sessionStorage.getItem(QUERY_KEY)).toBeNull()
  expect(window.sessionStorage.getItem(PAGE_KEY)).toBeNull()
  expect(window.sessionStorage.getItem(SCROLL_KEY)).toBeNull()
  expect(window.sessionStorage.getItem("theme")).toBe("dark")
  expect(window.sessionStorage.getItem("unrelated")).toBe("keep")
  expect(window.history.scrollRestoration).toBe("manual")
})

test("the actual reload boundary clears temporary queries while preserving account layout preferences", async () => {
  const key = "hede:account-preference:v1:1:purchase-order:detail-columns:v1"
  window.localStorage.setItem(key, JSON.stringify(["amount", "product_code"]))
  navigationType("reload")
  const { SessionPageStateBoundary } = await import("@/lib/session-page-state")
  render(<SessionPageStateBoundary><SessionQueryProvider userId={1}><QueryFixture /><LayoutPreferenceFixture /></SessionQueryProvider></SessionPageStateBoundary>)
  expect(screen.getByLabelText("筛选")).toHaveValue("")
  expect(screen.getByLabelText("页码")).toHaveTextContent("1")
  expect(window.sessionStorage.getItem(SCROLL_KEY)).toBeNull()
  expect(screen.getByLabelText("明细字段顺序")).toHaveTextContent("amount,product_code")
  expect(JSON.parse(window.localStorage.getItem(key)!)).toEqual(["amount", "product_code"])
  window.localStorage.removeItem(key)
})

test.each(["navigate", "back_forward"])("keeps saved filters and scroll positions on %s navigation", async (type) => {
  navigationType(type)
  const { SessionPageStateBoundary } = await import("@/lib/session-page-state")
  render(<SessionPageStateBoundary><SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider></SessionPageStateBoundary>)
  expect(screen.getByLabelText("筛选")).toHaveValue("已保存筛选")
  expect(screen.getByLabelText("页码")).toHaveTextContent("5")
  expect(JSON.parse(window.sessionStorage.getItem(SCROLL_KEY)!).window.top).toBe(1800)
})

test("only resets once after reload and preserves new page state across subsequent navigation and Strict Mode", async () => {
  const entries = navigationType("reload")
  const { SessionPageStateBoundary } = await import("@/lib/session-page-state")
  const view = render(<StrictMode><SessionPageStateBoundary><SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider></SessionPageStateBoundary></StrictMode>)
  fireEvent.change(screen.getByLabelText("筛选"), { target: { value: "刷新后的新筛选" } })
  window.sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ window: { top: 900, left: 0 }, containers: {} }))
  view.unmount()
  render(<SessionPageStateBoundary><SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider></SessionPageStateBoundary>)
  expect(screen.getByLabelText("筛选")).toHaveValue("刷新后的新筛选")
  expect(JSON.parse(window.sessionStorage.getItem(SCROLL_KEY)!).window.top).toBe(900)
  expect(entries).toHaveBeenCalledOnce()
})

test("missing navigation timing does not clear cache or prevent page rendering", async () => {
  Object.defineProperty(window.performance, "getEntriesByType", { configurable: true, value: undefined })
  const { SessionPageStateBoundary } = await import("@/lib/session-page-state")
  render(<SessionPageStateBoundary><SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider></SessionPageStateBoundary>)
  expect(screen.getByLabelText("筛选")).toHaveValue("已保存筛选")
  expect(window.sessionStorage.getItem(SCROLL_KEY)).not.toBeNull()
})

test("server rendering does not initialize or expose saved browser state", async () => {
  const entries = navigationType("reload")
  const { SessionPageStateBoundary } = await import("@/lib/session-page-state")
  expect(renderToString(<SessionPageStateBoundary><p>页面内容</p></SessionPageStateBoundary>)).toBe("")
  expect(entries).not.toHaveBeenCalled()
  expect(window.sessionStorage.getItem(QUERY_KEY)).not.toBeNull()
})
