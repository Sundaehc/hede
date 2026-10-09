import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { afterEach, expect, test, vi } from "vitest"

import { clearSessionQueryStates, SessionQueryProvider, useSessionQueryState } from "@/lib/session-query-state"

function QueryFixture({ pageKey = "products" }: { pageKey?: string }) {
  const [input, setInput] = useSessionQueryState(pageKey + ":input", "")
  const [query, setQuery] = useSessionQueryState(pageKey + ":query", "")
  const [page, setPage] = useSessionQueryState(pageKey + ":page", 1)
  const [filters, setFilters] = useSessionQueryState<string[]>(pageKey + ":filters", [])
  return <div>
    <input aria-label="查询条件" value={input} onChange={(event) => setInput(event.target.value)} />
    <output aria-label="已提交查询">{query}</output>
    <output aria-label="页码">{page}</output>
    <output aria-label="筛选">{filters.join(",")}</output>
    <button onClick={() => setQuery(input)}>搜索</button>
    <button onClick={() => { setPage((current) => current + 1); setPage((current) => current + 1) }}>翻页</button>
    <button onClick={() => setFilters(["烟斗", "客户店铺"])}>筛选</button>
    <button onClick={() => { setInput(""); setQuery(""); setFilters([]); setPage(1) }}>清空</button>
  </div>
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  clearSessionQueryStates()
})

test("restores query inputs, submitted filters and pagination after navigating away", () => {
  const first = render(<QueryFixture />)
  fireEvent.change(screen.getByLabelText("查询条件"), { target: { value: "SKU-123" } })
  fireEvent.click(screen.getByText("搜索"))
  fireEvent.click(screen.getByText("翻页"))
  fireEvent.click(screen.getByRole("button", { name: "筛选" }))
  fireEvent.change(screen.getByLabelText("查询条件"), { target: { value: "未提交草稿" } })
  first.unmount()

  const second = render(<QueryFixture pageKey="inventory" />)
  expect(screen.getByLabelText("查询条件")).toHaveValue("")
  second.unmount()

  render(<QueryFixture />)
  expect(screen.getByLabelText("查询条件")).toHaveValue("未提交草稿")
  expect(screen.getByLabelText("已提交查询")).toHaveTextContent("SKU-123")
  expect(screen.getByLabelText("页码")).toHaveTextContent("3")
  expect(screen.getByLabelText("筛选")).toHaveTextContent("烟斗,客户店铺")
})

test("clear stays cleared after returning and a new browser session starts at defaults", () => {
  const first = render(<QueryFixture />)
  fireEvent.change(screen.getByLabelText("查询条件"), { target: { value: "SKU" } })
  fireEvent.click(screen.getByText("搜索"))
  fireEvent.click(screen.getByText("清空"))
  first.unmount()
  const second = render(<QueryFixture />)
  expect(screen.getByLabelText("查询条件")).toHaveValue("")
  fireEvent.change(screen.getByLabelText("查询条件"), { target: { value: "SKU" } })
  second.unmount()
  window.sessionStorage.clear()
  render(<QueryFixture />)
  expect(screen.getByLabelText("查询条件")).toHaveValue("")
})

test("isolates users and clears only query storage on logout", () => {
  window.sessionStorage.setItem("other-session-data", "retain")
  const first = render(<SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider>)
  fireEvent.change(screen.getByLabelText("查询条件"), { target: { value: "user-one" } })
  first.unmount()
  const second = render(<SessionQueryProvider userId={2}><QueryFixture /></SessionQueryProvider>)
  expect(screen.getByLabelText("查询条件")).toHaveValue("")
  second.unmount()
  const third = render(<SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider>)
  expect(screen.getByLabelText("查询条件")).toHaveValue("user-one")
  act(() => clearSessionQueryStates())
  expect(screen.getByLabelText("查询条件")).toHaveValue("")
  expect(window.sessionStorage.getItem("other-session-data")).toBe("retain")
  third.unmount()
})

test("handles corrupt storage and blocked browser storage without losing navigation state", () => {
  window.sessionStorage.setItem("hede:session-query:v1:anonymous:products:filters", "invalid-json")
  const first = render(<QueryFixture />)
  expect(screen.getByLabelText("筛选")).toBeEmptyDOMElement()
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage blocked") })
  fireEvent.change(screen.getByLabelText("查询条件"), { target: { value: "fallback" } })
  first.unmount()
  render(<QueryFixture />)
  expect(screen.getByLabelText("查询条件")).toHaveValue("fallback")
})

test("does not render cached browser queries into server HTML", () => {
  window.sessionStorage.setItem("hede:session-query:v1:1:products:input", JSON.stringify("private-query"))
  expect(renderToString(<SessionQueryProvider userId={1}><QueryFixture /></SessionQueryProvider>)).not.toContain("private-query")
})
