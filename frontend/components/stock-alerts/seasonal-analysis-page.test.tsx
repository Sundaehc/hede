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
import { SeasonalAnalysisPage } from "./seasonal-analysis-page"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import { clearStockModuleQueries } from "@/lib/stock-module-query"
import type {
  SeasonalFilters,
  SeasonalResponse,
  SeasonalSummary,
} from "@/lib/seasonal-analysis"

const { load, options, review } = vi.hoisted(() => ({
  load: vi.fn(),
  options: vi.fn(),
  review: vi.fn(),
}))
vi.mock("@/lib/api", () => ({
  getSeasonalAnalysis: load,
  getSeasonalItemReview: review,
  getStockAlertOptions: options,
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 101, permissions: ["product.view"] } }),
}))

function response(page = 1): SeasonalResponse {
  const summary: SeasonalSummary = {
    quarter: 4,
    cutoff: "2026-11-16",
    state: "available",
    missing_days: 0,
    product_count: 30,
    gross_sales: 200,
    net_sales: 180,
    period_net_sales: 180,
    sales_share: 20,
    inbound_quantity: "500",
    received_quantity: "600",
    sell_through_rate: 30,
    single_order_count: 12,
    multiple_order_count: 18,
    unknown_order_count: 0,
  }
  return {
    year: 2026,
    quarter: 4,
    summary,
    quarters: [1, 2, 3, 4].map((quarter) => ({ ...summary, quarter })),
    order_groups: [
      { ...summary, order_state: "single" },
      { ...summary, order_state: "multiple" },
    ],
    activity: [
      {
        days: 3,
        eligible: 30,
        valid: 28,
        active: 14,
        pending: 2,
        immature: 0,
        rate: 50,
      },
    ],
    trend: [
      { date: "2026-10-01", gross: 10, net: 8 },
      { date: "2026-10-02", gross: null, net: null },
    ],
    items: [
      {
        id: page,
        sku: "SYNTHETIC-" + page,
        original_sku: null,
        product_name: "合成商品",
        color: "黑色",
        season: "冬",
        launch_date: "2026-10-01",
        listed_days: 47,
        available_quantity: "0",
        order_state: "single",
        inbound_dates: ["2026-11-10", "2026-10-20", "2026-09-15"],
        pending_reasons: [],
        gross_sales: 10,
        net_sales: 9,
        received_quantity: "30",
        inbound_quantity: "30",
        sell_through_rate: 30,
      },
    ],
    total: 30,
    page,
    page_size: 25,
    counts: { all: 30, single: 12, pending: 2, arrivals: 1, zero: 2 },
    followup_ready: { arrivals: true, zero: true },
    sales_end: "2026-11-16",
    stock_date: "2026-11-17",
    seasons: ["冬"],
    years: [2026, 2025],
    source_issues: ["售罄率为采购入库参考"],
    missing_launch_count: 5,
    unmatched_stock_rows: 2,
    unmatched_purchase_rows: 1,
    purchase_ready: true,
  }
}

function deferred() {
  let resolve!: (value: SeasonalResponse) => void
  let reject!: (error: Error) => void
  const promise = new Promise<SeasonalResponse>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.resetAllMocks()
  clearSessionQueryStates()
  clearStockModuleQueries()
  options.mockResolvedValue({
    brands: [{ value: "cbanner_mens", label: "千百度男鞋" }],
  })
  load.mockImplementation((filters) => Promise.resolve(response(filters.page)))
})
afterEach(cleanup)

test("submits draft filters, preserves summary on pagination, and refreshes facts explicitly", async () => {
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: " draft " },
  })
  expect(load).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  await screen.findByText("SYNTHETIC-2")
  expect(load.mock.calls[1][0]).toMatchObject({ page: 2, query: "" })
  expect(screen.getByLabelText("季度经营概览")).toHaveTextContent("季度新品30")
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() =>
    expect(load.mock.calls.at(-1)?.[0]).toMatchObject({
      page: 1,
      query: "draft",
    })
  )
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  )
  fireEvent.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(load.mock.calls.at(-1)?.[1]?.refresh).toBe(true))
})

test("switches cohorts and order filters without changing committed search", async () => {
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: "unsent" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Q2" }))
  await waitFor(() =>
    expect(load.mock.calls.at(-1)?.[0]).toMatchObject({
      quarter: 2,
      query: "",
      page: 1,
    })
  )
  fireEvent.click(screen.getByRole("button", { name: /仅首单未补货/ }))
  await waitFor(() =>
    expect(load.mock.calls.at(-1)?.[0]).toMatchObject({
      quarter: 2,
      status: "single",
      query: "",
    })
  )
})

test("renders missing values as unknown and keeps sold-out products", async () => {
  const value = response()
  value.summary.sell_through_rate = null
  value.items[0].net_sales = null
  value.items[0].pending_reasons = ["日销缺少1天"]
  load.mockResolvedValue(value)
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  expect(screen.getByLabelText("季度经营概览")).toHaveTextContent(
    "整体参考售罄率—"
  )
  expect(screen.getByText("日销缺少1天")).toBeInTheDocument()
  expect(screen.getByText("10 / —")).toBeInTheDocument()
})

test("shows actual inbound dates and expands older receipt days", async () => {
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  expect(
    screen.getByRole("columnheader", { name: "入库日期" })
  ).toBeInTheDocument()
  expect(
    screen.queryByRole("columnheader", { name: "采购记录" })
  ).not.toBeInTheDocument()
  const row = screen.getByRole("row", { name: /SYNTHETIC-1/ })
  expect(within(row).getByText("2026-11-10")).toBeVisible()
  expect(within(row).getByText("2026-10-20")).toBeVisible()
  expect(within(row).getByText("2026-09-15")).not.toBeVisible()
  fireEvent.click(within(row).getByText("其余 1 个入库日期"))
  expect(within(row).getByText("2026-09-15")).toBeVisible()
  expect(within(row).queryByText("仅首单")).not.toBeInTheDocument()
})

test.each([true, false])(
  "shows an explicit receipt empty state when purchase ready is %s",
  async (ready) => {
    const value = response()
    value.items[0].inbound_dates = []
    value.purchase_ready = ready
    load.mockResolvedValue(value)
    render(<SeasonalAnalysisPage />)
    await screen.findByText("SYNTHETIC-1")
    const row = screen.getByRole("row", { name: /SYNTHETIC-1/ })
    expect(
      within(row).getByText(ready ? "暂无入库记录" : "入库数据未就绪")
    ).toBeInTheDocument()
  }
)

test("loads one product review on demand and opens the purchase receipt detail", async () => {
  review.mockResolvedValue({
    first_inbound_date: "2026-09-15",
    launch_date: "2026-10-01",
    show_receipt_numbers: true,
    receipt_end: "2026-11-16",
    sales: {
      start: "2026-10-01",
      end: "2026-11-16",
      first_sale_date: "2026-10-03",
      missing_days: 0,
      channels: [{ channel: "唯品", gross_sales: 10, net_sales: 9 }],
    },
    receipts: {
      total: 1,
      page: 1,
      pages: 1,
      quantity: "30",
      items: [
        {
          inbound_date: "2026-11-10",
          purchase_order_id: null,
          inbound_id: "IN-024",
          quantity: "30",
        },
      ],
    },
  })
  render(<SeasonalAnalysisPage />)
  const button = await screen.findByRole("button", {
    name: /查看 SYNTHETIC-1 本季进货明细/,
  })
  expect(review).not.toHaveBeenCalled()
  fireEvent.click(button)
  const dialog = await screen.findByRole("dialog", {
    name: "单款复盘 · SYNTHETIC-1",
  })
  expect(await within(dialog).findByText("IN-024")).toBeVisible()
  expect(within(dialog).getByText("未提供")).toBeVisible()
  expect(within(dialog).getByText("唯品")).toBeVisible()
  expect(within(dialog).getByText("2026-10-03")).toBeVisible()
  expect(review).toHaveBeenCalledWith(
    expect.objectContaining({ brand: "cbanner_mens" }),
    1,
    1,
    expect.any(AbortSignal)
  )
  fireEvent.click(within(dialog).getByRole("button", { name: "关闭复盘" }))
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  expect(load).toHaveBeenCalledTimes(1)
})

test("keeps missing launch dates separate from confirmed zero sales", async () => {
  load.mockImplementation(async (filters) => {
    const result = response()
    if (filters.status === "arrivals") {
      result.items[0] = {
        ...result.items[0],
        sku: "ARRIVED",
        launch_date: null,
        inbound_quantity: null,
        listed_days: null,
        gross_sales: null,
        net_sales: null,
        pending_reasons: ["档案未填上市日期"],
      }
    } else if (filters.status === "zero") {
      result.items[0] = {
        ...result.items[0],
        sku: "ZERO",
        gross_sales: 0,
        net_sales: 0,
        available_quantity: "4",
      }
    }
    return result
  })
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  fireEvent.click(screen.getByRole("button", { name: /到货待补上市日期/ }))
  await screen.findByText("ARRIVED")
  expect(screen.getByText("档案未填上市日期")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: /上市满 15 天零动销/ }))
  await screen.findByText("ZERO")
  expect(screen.queryByText("ARRIVED")).not.toBeInTheDocument()
  expect(screen.getByLabelText("季度经营概览")).toHaveTextContent("季度新品30")
})

test.each([
  ["品牌", "smiley"],
  ["上市年份", "2025"],
  ["上市季度", "2"],
  ["季节", "冬"],
  ["商品搜索", "another product"],
])("hides old analysis while querying a new %s scope", async (label, value) => {
  options.mockResolvedValue({
    brands: [
      { value: "cbanner_mens", label: "千百度男鞋" },
      { value: "smiley", label: "笑脸" },
    ],
  })
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  const pending = deferred()
  load.mockReturnValueOnce(pending.promise)
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))

  expect(screen.queryByText("SYNTHETIC-1")).not.toBeInTheDocument()
  expect(screen.getByLabelText("季度经营概览")).toHaveAttribute(
    "aria-busy",
    "true"
  )
  expect(screen.getByLabelText("季度经营概览")).not.toHaveTextContent(
    "季度新品30"
  )
  expect(screen.getByLabelText("上市后动销观察")).not.toHaveTextContent(
    "已动销 0"
  )
  expect(screen.queryByText(/暂时保留上次分析结果/)).not.toBeInTheDocument()
  expect(screen.queryByText(/另有 5 项商品缺少/)).not.toBeInTheDocument()
  expect(screen.getByText("正在查询季度分析…")).toBeVisible()
  expect(screen.getByRole("button", { name: "查询中…" })).toBeDisabled()
  fireEvent.submit(
    screen.getByRole("button", { name: "查询中…" }).closest("form")!
  )
  expect(load).toHaveBeenCalledTimes(2)

  const filters = load.mock.lastCall![0] as SeasonalFilters
  const result = response()
  result.year = filters.year
  result.quarter = result.summary.quarter = filters.quarter
  result.summary.product_count = 45
  result.items[0].sku = "NEW-SCOPE"
  await act(async () => pending.resolve(result))
  expect(screen.getByText("NEW-SCOPE")).toBeVisible()
  expect(screen.getByLabelText("季度经营概览")).toHaveTextContent("季度新品45")
  expect(screen.getByLabelText("季度经营概览")).toHaveAttribute(
    "aria-busy",
    "false"
  )
  expect(screen.getByRole("button", { name: "查询" })).toBeEnabled()
})

test("keeps the overview stable and replaces old rows with skeletons during pagination", async () => {
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  const pending = deferred()
  load.mockReturnValueOnce(pending.promise)
  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))

  expect(screen.getByLabelText("季度经营概览")).toHaveTextContent("季度新品30")
  expect(screen.getByLabelText("季度经营概览")).toHaveAttribute(
    "aria-busy",
    "false"
  )
  expect(screen.getByLabelText("新品销售趋势")).toHaveAttribute(
    "aria-busy",
    "false"
  )
  expect(
    screen.getByRole("img", { name: "季度新品每日销售趋势" })
  ).toBeVisible()
  expect(screen.getByLabelText("新品商品明细")).toHaveAttribute(
    "aria-busy",
    "true"
  )
  expect(screen.queryByText("SYNTHETIC-1")).not.toBeInTheDocument()
  expect(screen.getByText("正在加载第 2 页明细…")).toBeVisible()
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled()

  await act(async () => pending.resolve(response(2)))
  expect(screen.getByText("SYNTHETIC-2")).toBeVisible()
  expect(screen.getByLabelText("新品商品明细")).toHaveAttribute(
    "aria-busy",
    "false"
  )
})

test.each(["仅首单未补货", "到货待补上市日期", "上市满 15 天零动销"])(
  "only reloads detail rows when switching to %s",
  async (name) => {
    render(<SeasonalAnalysisPage />)
    await screen.findByText("SYNTHETIC-1")
    const pending = deferred()
    load.mockReturnValueOnce(pending.promise)
    fireEvent.click(screen.getByRole("button", { name: new RegExp(name) }))
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
    expect(screen.getByLabelText("季度经营概览")).toHaveTextContent(
      "季度新品30"
    )
    expect(screen.getByLabelText("跨季度对比")).toHaveAttribute(
      "aria-busy",
      "false"
    )
    expect(screen.queryByText("SYNTHETIC-1")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: new RegExp(name) })
    ).toBeDisabled()
    const result = response()
    result.items[0].sku = "FILTERED-ROW"
    await act(async () => pending.resolve(result))
    expect(screen.getByText("FILTERED-ROW")).toBeVisible()
  }
)

test("retains current results during refresh and recovers from a failed new scope", async () => {
  render(<SeasonalAnalysisPage />)
  await screen.findByText("SYNTHETIC-1")
  const refreshed = deferred()
  load.mockReturnValueOnce(refreshed.promise)
  fireEvent.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  expect(screen.getByText("SYNTHETIC-1")).toBeVisible()
  expect(screen.getByLabelText("季度经营概览")).toHaveTextContent("季度新品30")
  expect(screen.getByText("正在刷新当前分析…")).toBeVisible()
  await act(async () => refreshed.resolve(response()))

  const failed = deferred()
  load.mockReturnValueOnce(failed.promise)
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: "new" },
  })
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  await act(async () => failed.reject(new Error("查询超时")))
  expect(screen.getByRole("alert")).toHaveTextContent("查询超时")
  expect(screen.queryByText("SYNTHETIC-1")).not.toBeInTheDocument()
  expect(screen.getByText("分析暂不可用")).toBeVisible()
  expect(screen.getByRole("button", { name: "查询" })).toBeEnabled()

  const retried = deferred()
  load.mockReturnValueOnce(retried.promise)
  fireEvent.click(screen.getByRole("button", { name: "重试" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(4))
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  expect(screen.getByLabelText("季度经营概览")).toHaveAttribute(
    "aria-busy",
    "true"
  )
  expect(screen.getByRole("button", { name: "查询中…" })).toBeDisabled()
  const result = response()
  result.items[0].sku = "RECOVERED"
  await act(async () => retried.resolve(result))
  expect(screen.getByText("RECOVERED")).toBeVisible()
})
