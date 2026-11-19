import { StrictMode } from "react"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import { publishBusinessDataChange } from "./business-data-sync"
import {
  clearStockModuleQueries,
  loadStockModuleQuery,
  readStockModuleQuery,
} from "./stock-module-cache"
import {
  STOCK_ALERT_RESOURCES,
  STOCK_SOURCE_RESOURCES,
  useStockModuleOptions,
  useStockModuleQuery,
} from "./stock-module-query"

const auth = vi.hoisted(() => ({ id: 1, permissions: ["product.view"] }))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: auth }),
}))
const load =
  vi.fn<
    (signal: AbortSignal, refreshFacts: boolean) => Promise<{ label: string }>
  >()
let clock = 1_794_868_200_000

function Page({
  page = "1",
  revision = 0,
  previousDataKey,
}: {
  page?: string
  revision?: number
  previousDataKey?: string
}) {
  const query = useStockModuleQuery({
    group: "alerts",
    queryKey: page,
    previousDataKey,
    revision,
    resources: STOCK_ALERT_RESOURCES,
    factResources: STOCK_SOURCE_RESOURCES,
    load,
  })
  return (
    <div>
      <span>{query.data?.label ?? "loading"}</span>
      <span>{query.refreshing ? "refreshing" : "ready"}</span>
      <span>{query.error}</span>
      <span
        data-testid="previous-result"
        data-value={query.previousData?.label}
      />
    </div>
  )
}

beforeEach(() => {
  clearStockModuleQueries()
  window.localStorage.clear()
  auth.id = 1
  auth.permissions = ["product.view"]
  load.mockReset().mockResolvedValue({ label: "first" })
  clock = 1_794_868_200_000
  vi.spyOn(Date, "now").mockImplementation(() => clock)
})
afterEach(() => {
  cleanup()
  clearStockModuleQueries()
  vi.restoreAllMocks()
})

test("restores a fresh page immediately without another request", async () => {
  const first = render(<Page />)
  await screen.findByText("first")
  first.unmount()
  render(<Page />)
  expect(screen.getByText("first")).toBeInTheDocument()
  await act(async () => {})
  expect(load).toHaveBeenCalledTimes(1)
})

test("only retains previous data from the same display scope and ignores late responses", async () => {
  const view = render(<Page previousDataKey="brand-a" />)
  await screen.findByText("first")
  let finishOld!: (value: { label: string }) => void
  load.mockReturnValueOnce(
    new Promise((resolve) => {
      finishOld = resolve
    })
  )
  view.rerender(<Page page="2" previousDataKey="brand-a" />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  expect(screen.getByTestId("previous-result")).toHaveAttribute(
    "data-value",
    "first"
  )

  let finishNew!: (value: { label: string }) => void
  load.mockReturnValueOnce(
    new Promise((resolve) => {
      finishNew = resolve
    })
  )
  view.rerender(<Page page="3" previousDataKey="brand-b" />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  expect(screen.getByTestId("previous-result")).not.toHaveAttribute(
    "data-value"
  )
  await act(async () => finishNew({ label: "new scope" }))
  await act(async () => finishOld({ label: "late result" }))
  expect(screen.queryByText("late result")).not.toBeInTheDocument()
  expect(screen.getByText("new scope")).toBeVisible()
})

test("keeps expired results visible while revalidating and replaces them", async () => {
  const first = render(<Page />)
  await screen.findByText("first")
  first.unmount()
  clock += 30_001
  let done!: (value: { label: string }) => void
  load.mockReturnValueOnce(
    new Promise((resolve) => {
      done = resolve
    })
  )
  render(<Page />)
  expect(screen.getByText("first")).toBeInTheDocument()
  expect(screen.getByText("refreshing")).toBeInTheDocument()
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  await act(async () => done({ label: "second" }))
  expect(screen.getByText("second")).toBeInTheDocument()
  expect(screen.getByText("ready")).toBeInTheDocument()
})

test("does not restore results past the retention period or across a business day", async () => {
  const first = render(<Page />)
  await screen.findByText("first")
  first.unmount()
  clock += 86_400_000
  load.mockReturnValueOnce(new Promise(() => {}))
  render(<Page />)
  expect(screen.queryByText("first")).not.toBeInTheDocument()
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
})

test("isolates cached results by account and permissions", async () => {
  const first = render(<Page />)
  await screen.findByText("first")
  first.unmount()
  auth.id = 2
  load.mockResolvedValueOnce({ label: "other" })
  const second = render(<Page />)
  expect(screen.queryByText("first")).not.toBeInTheDocument()
  await screen.findByText("other")
  second.unmount()
  auth.permissions = ["product.view", "product.manage"]
  render(<Page />)
  expect(screen.queryByText("other")).not.toBeInTheDocument()
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
})

test("detects source writes while unmounted and bypasses backend facts", async () => {
  const first = render(<Page />)
  await screen.findByText("first")
  first.unmount()
  publishBusinessDataChange(["products"])
  load.mockResolvedValueOnce({ label: "new product" })
  render(<Page />)
  expect(screen.queryByText("first")).not.toBeInTheDocument()
  await screen.findByText("new product")
  expect(load.mock.calls[1][1]).toBe(true)
})

test("rule and task changes invalidate results while reusing backend facts", async () => {
  for (const resource of ["stock-alert-rules", "stock-alert-tasks"] as const) {
    const first = render(<Page />)
    await screen.findByText("first")
    first.unmount()
    publishBusinessDataChange([resource])
    const count = load.mock.calls.length
    const second = render(<Page />)
    await screen.findByText("first")
    expect(load).toHaveBeenCalledTimes(count + 1)
    expect(load.mock.lastCall?.[1]).toBe(false)
    second.unmount()
  }
})

test("refresh invalidates other pages in the same module", async () => {
  const view = render(<Page />)
  await screen.findByText("first")
  view.rerender(<Page page="2" />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  await screen.findByText("ready")
  view.rerender(<Page />)
  await act(async () => {})
  expect(load).toHaveBeenCalledTimes(2)
  view.rerender(<Page revision={1} />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  await screen.findByText("ready")
  view.rerender(<Page page="2" revision={1} />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(4))
})

test("shares brand options and Strict Mode requests", async () => {
  const options = vi
    .fn()
    .mockResolvedValue({ brands: [{ value: "demo", label: "品牌" }] })
  function Options() {
    const query = useStockModuleOptions(options)
    return <span>{query.data?.brands[0].label}</span>
  }
  render(
    <StrictMode>
      <Options />
      <Options />
      <Page />
    </StrictMode>
  )
  await waitFor(() => expect(screen.getAllByText("品牌")).toHaveLength(2))
  expect(options).toHaveBeenCalledTimes(1)
  expect(load).toHaveBeenCalledTimes(1)
})

test("one observer abort does not cancel the shared request for another", async () => {
  let finish!: (value: { label: string }) => void
  const loader = vi.fn(
    (signal: AbortSignal) =>
      new Promise<{ label: string }>((resolve) => {
        finish = resolve
        expect(signal.aborted).toBe(false)
      })
  )
  const a = new AbortController(),
    b = new AbortController()
  const first = loadStockModuleQuery(
    "shared",
    "family",
    loader,
    a.signal,
    30_000,
    60_000
  )
  const rejected = expect(first).rejects.toMatchObject({ name: "AbortError" })
  const second = loadStockModuleQuery(
    "shared",
    "family",
    loader,
    b.signal,
    30_000,
    60_000
  )
  await Promise.resolve()
  a.abort()
  await rejected
  expect(loader.mock.calls[0][0].aborted).toBe(false)
  finish({ label: "shared" })
  expect(await second).toEqual({ label: "shared" })
  expect(loader).toHaveBeenCalledTimes(1)
})

test("does not retain failed requests or responses arriving after logout", async () => {
  const controller = new AbortController()
  const bad = () => Promise.reject(new Error("failed"))
  await expect(
    loadStockModuleQuery("bad", "f", bad, controller.signal, 30_000, 60_000)
  ).rejects.toThrow("failed")
  expect(readStockModuleQuery("bad")).toBeNull()
  let finish!: (value: string) => void
  const old = loadStockModuleQuery(
    "old",
    "f",
    () =>
      new Promise<string>((resolve) => {
        finish = resolve
      }),
    controller.signal,
    30_000,
    60_000
  )
  await Promise.resolve()
  clearStockModuleQueries()
  finish("private")
  await old
  expect(readStockModuleQuery("old")).toBeNull()
})

test("bounds cached pages by count and payload size", async () => {
  for (let i = 0; i < 40; i++)
    await loadStockModuleQuery(
      String(i),
      "f",
      async () => i,
      new AbortController().signal,
      30_000,
      60_000
    )
  expect(readStockModuleQuery("0")).toBeNull()
  expect(readStockModuleQuery<number>("39")?.data).toBe(39)
  await loadStockModuleQuery(
    "huge",
    "f",
    async () => "a".repeat(3 * 1024 * 1024),
    new AbortController().signal,
    30_000,
    60_000
  )
  expect(readStockModuleQuery("huge")).toBeNull()
})
