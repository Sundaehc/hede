import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import {
  clearSessionQueryStates,
  SessionQueryProvider,
  useAccountPreferenceState,
  useSessionQueryState,
} from "./session-query-state"

const KEY = "hede:account-preference:v1:1:detail-columns"

function Preferences({
  preferenceKey = "detail-columns",
}: {
  preferenceKey?: string
}) {
  const [fields, setFields] = useAccountPreferenceState<string[]>(
    preferenceKey,
    ["货号", "金额"]
  )
  const [query, setQuery] = useSessionQueryState("inventory:query", "")
  return (
    <>
      <output aria-label="字段顺序">{fields.join(",")}</output>
      <input
        aria-label="查询"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <button onClick={() => setFields(["金额", "货号"])}>应用顺序</button>
    </>
  )
}
function fixture(userId = 1, preferenceKey?: string) {
  return (
    <SessionQueryProvider userId={userId}>
      <Preferences preferenceKey={preferenceKey} />
    </SessionQueryProvider>
  )
}

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test("preferences survive refresh cleanup and a new session while remaining isolated between accounts", () => {
  const first = render(fixture())
  fireEvent.click(screen.getByRole("button", { name: "应用顺序" }))
  fireEvent.change(screen.getByLabelText("查询"), {
    target: { value: "临时筛选" },
  })
  expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual([
    "金额",
    "货号",
  ])
  act(() => clearSessionQueryStates())
  expect(screen.getByLabelText("查询")).toHaveValue("")
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
  first.unmount()
  window.sessionStorage.clear()
  const reopened = render(fixture())
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
  reopened.rerender(fixture(2))
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("货号,金额")
  reopened.rerender(fixture())
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
})

test("same-account preference changes from another browser tab update the mounted view", () => {
  render(fixture())
  window.localStorage.setItem(KEY, JSON.stringify(["金额", "货号"]))
  act(() => window.dispatchEvent(new StorageEvent("storage", { key: KEY })))
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
  const otherKey = KEY.replace(":1:", ":2:")
  window.localStorage.setItem(otherKey, JSON.stringify(["其他账号字段"]))
  act(() =>
    window.dispatchEvent(new StorageEvent("storage", { key: otherKey }))
  )
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
})

test("corrupt preferences fall back safely and browser values are absent from server HTML", () => {
  window.localStorage.setItem(KEY, "bad-json")
  const view = render(fixture())
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("货号,金额")
  view.unmount()
  window.localStorage.setItem(
    "hede:account-preference:v1:anonymous:detail-columns",
    JSON.stringify(["saved-only-in-browser"])
  )
  expect(renderToString(<Preferences />)).not.toContain("saved-only-in-browser")
})

test("blocked storage keeps the applied preference usable across navigation and temporary-state cleanup", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Storage blocked")
  })
  const first = render(fixture(1, "blocked-fields"))
  fireEvent.click(screen.getByRole("button", { name: "应用顺序" }))
  act(() => clearSessionQueryStates())
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
  first.unmount()
  render(fixture(1, "blocked-fields"))
  expect(screen.getByLabelText("字段顺序")).toHaveTextContent("金额,货号")
})
