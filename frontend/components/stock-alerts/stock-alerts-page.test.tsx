import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import { StockAlertsPage } from "./stock-alerts-page"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import type { StockAlertResponse } from "@/lib/stock-alerts"

const { load, options, save, canManage } = vi.hoisted(() => ({
  load: vi.fn(),
  options: vi.fn(),
  save: vi.fn(),
  canManage: { value: true },
}))
vi.mock("@/lib/api", () => ({
  getStockAlerts: load,
  getStockAlertOptions: options,
  saveStockAlertRule: save,
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ hasPermission: () => canManage.value }),
}))

function response(total = 30): StockAlertResponse {
  return {
    items: [],
    total,
    page: 1,
    page_size: 25,
    counts: { warning: 3, pending: 2 },
    warning_stock: "100",
    stock_products: 10,
    seasons: ["冬"],
    stock_date: "2026-11-13",
    sales_end: "2026-11-12",
    source_issues: ["采购退货不全，售罄率仅供参考"],
    unmatched_stock_rows: 0,
    ready: true,
    rule: { age_days: 60, rate: "20", version: 0, source: "default" },
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  clearSessionQueryStates()
  canManage.value = true
  options.mockResolvedValue({
    brands: [
      { value: "cbanner_mens", label: "千百度男鞋" },
      { value: "cbanner_womens", label: "千百度女鞋" },
    ],
  })
  load.mockResolvedValue(response())
  save.mockResolvedValue({ message: "已保存" })
})
afterEach(cleanup)

test("keeps submitted queries separate from drafts and restores each menu independently", async () => {
  const view = render(<StockAlertsPage kind="zero" />)
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  )
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: " ABC " },
  })
  fireEvent.change(screen.getByLabelText("季节"), { target: { value: "冬" } })
  expect(load).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  expect(load.mock.calls[1][0]).toMatchObject({
    query: "ABC",
    season: "冬",
    page: 1,
  })
  view.rerender(<StockAlertsPage kind="slow" />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  expect(load.mock.calls[2].slice(0, 2)).toEqual([
    expect.objectContaining({ query: "", season: "" }),
    "slow",
  ])
  view.rerender(<StockAlertsPage kind="zero" />)
  await waitFor(() => expect(load).toHaveBeenCalledTimes(4))
  expect(load.mock.calls[3][0]).toMatchObject({ query: "ABC", season: "冬" })
})

test("cancels superseded requests and ignores a late response", async () => {
  render(<StockAlertsPage kind="slow" />)
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  )
  let resolve!: (value: StockAlertResponse) => void
  load.mockReturnValueOnce(
    new Promise<StockAlertResponse>((done) => {
      resolve = done
    })
  )
  fireEvent.change(screen.getByLabelText("品牌"), {
    target: { value: "cbanner_womens" },
  })
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  const signal = load.mock.calls[1][2].signal as AbortSignal
  fireEvent.click(screen.getByRole("button", { name: /数据待核对/ }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  expect(signal.aborted).toBe(true)
  await act(async () => resolve(response(999)))
  expect(screen.queryByText(/共 999 项/)).not.toBeInTheDocument()
  expect(load.mock.calls[2][0]).toMatchObject({
    brand: "cbanner_womens",
    status: "pending",
    page: 1,
  })
})

test("paginates using submitted conditions and bypasses facts cache only on refresh", async () => {
  render(<StockAlertsPage kind="zero" />)
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled()
  )
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: "draft" },
  })
  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  expect(load.mock.calls[1][0]).toMatchObject({ query: "", page: 2 })
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  )
  fireEvent.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  expect(load.mock.calls[2][2].refresh).toBe(true)
})

test("saves seasonal rules in the committed scope and preserves draft on conflict", async () => {
  render(<StockAlertsPage kind="slow" />)
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "设置规则" })).toBeEnabled()
  )
  fireEvent.change(screen.getByLabelText("季节"), { target: { value: "冬" } })
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "设置规则" })).toBeEnabled()
  )
  fireEvent.change(screen.getByLabelText("品牌"), {
    target: { value: "cbanner_womens" },
  })
  fireEvent.click(screen.getByRole("button", { name: "设置规则" }))
  const dialog = within(screen.getByRole("dialog"))
  expect(dialog.getByText("千百度男鞋 · 冬")).toBeInTheDocument()
  fireEvent.change(dialog.getByLabelText("上市天数"), {
    target: { value: "90" },
  })
  fireEvent.change(dialog.getByLabelText("售罄率阈值"), {
    target: { value: "15" },
  })
  save.mockRejectedValueOnce(new Error("规则已被其他页面修改，请刷新"))
  fireEvent.click(dialog.getByRole("button", { name: "保存规则" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "规则已被其他页面修改"
  )
  expect(dialog.getByLabelText("上市天数")).toHaveValue(90)
  expect(save).toHaveBeenCalledWith({
    brand: "cbanner_mens",
    season: "冬",
    kind: "slow",
    age_days: 90,
    rate: "15",
    version: 0,
  })
  fireEvent.click(dialog.getByRole("button", { name: "保存规则" }))
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  )
})

test("view-only users cannot edit rules and missing sources do not appear as zero alerts", async () => {
  canManage.value = false
  load.mockResolvedValue({
    ...response(0),
    ready: false,
    stock_date: null,
    sales_end: null,
  })
  render(<StockAlertsPage kind="zero" />)
  expect(
    await screen.findByText("数据源未就绪，请先补齐库存及日销")
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "设置规则" })
  ).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: /待跟进商品/ })).toHaveTextContent(
    "—"
  )
})
