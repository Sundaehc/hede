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
import { ReplenishmentPage } from "./replenishment-page"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import type { ReplenishmentResponse } from "@/lib/stock-replenishment"

const { load, options, getRule, save, permission } = vi.hoisted(() => ({
  load: vi.fn(),
  options: vi.fn(),
  getRule: vi.fn(),
  save: vi.fn(),
  permission: { manage: true },
}))
vi.mock("@/lib/api", () => ({
  getReplenishment: load,
  getStockAlertOptions: options,
  getReplenishmentRule: getRule,
  saveReplenishmentRule: save,
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({
    hasPermission: (value: string) =>
      value !== "product.manage" || permission.manage,
  }),
}))

function response(): ReplenishmentResponse {
  const summary = {
    supplier: "工厂甲",
    suggested_quantity: 70,
    suggested_products: 2,
    pending_products: 0,
    min_order_qty: 100,
    moq_gap: 30,
    meets_moq: false,
  }
  return {
    items: [
      {
        id: 1,
        sku: "A",
        original_sku: "原始A",
        product_name: "休闲鞋",
        color: "黑",
        supplier: "工厂甲",
        size_group: "女鞋",
        available_quantity: "5",
        purchase_in_transit: "6",
        net_sales: "60",
        sales_returns: "0",
        observation_days: 30,
        daily_sales: "2",
        stock_days: "2.5",
        suggested_quantity: 35,
        lead_days: 10,
        cover_days: 10,
        pending_reasons: [],
        supplier_summary: summary,
        size_details: [
          {
            name: "35",
            ratio: 1,
            available_quantity: "5",
            purchase_in_transit: "6",
            daily_demand: "1",
            stock_days: "5",
            at_risk: true,
            suggested_quantity: 15,
          },
        ],
      },
    ],
    total: 30,
    page: 1,
    page_size: 25,
    counts: { suggested: 2, pending: 1, all: 3 },
    suggested_quantity: 70,
    supplier_summaries: [summary],
    supplier_options: {
      工厂甲: {
        女鞋: [
          { name: "35", barcode: "035" },
          { name: "36", barcode: "036" },
        ],
      },
    },
    window_days: 30,
    stock_date: "2026-11-14",
    sales_start: "2026-10-15",
    sales_end: "2026-11-13",
    ready: true,
    source_issues: ["尺码需求按配比估算"],
    unmatched_stock_rows: 0,
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  clearSessionQueryStates()
  permission.manage = true
  options.mockResolvedValue({
    brands: [
      { value: "cbanner_mens", label: "千百度男鞋" },
      { value: "cbanner_womens", label: "千百度女鞋" },
    ],
  })
  load.mockResolvedValue(response())
  getRule.mockResolvedValue({
    rule: null,
    groups: response().supplier_options["工厂甲"],
  })
  save.mockResolvedValue({ message: "已保存" })
})
afterEach(cleanup)

test("keeps supplier MOQ as returned for the whole supplier rather than the visible item", async () => {
  render(<ReplenishmentPage />)
  await screen.findByText("A")
  expect(screen.getByText("35 双")).toBeInTheDocument()
  expect(screen.getByText("供应商合计 70 双")).toBeInTheDocument()
  expect(screen.getAllByText("未达起订量，还差 30 双")).not.toHaveLength(0)
  fireEvent.click(screen.getByText("查看 1 个尺码"))
  expect(screen.getByText(/建议 15 双/)).toHaveTextContent("35 · 建议 15 双")
})

test("drafts apply only on query; pagination retains committed window and transit assumptions", async () => {
  render(<ReplenishmentPage />)
  await screen.findByText("A")
  fireEvent.change(screen.getByLabelText("供应商"), {
    target: { value: "工厂甲" },
  })
  fireEvent.change(screen.getByLabelText("销量统计天数"), {
    target: { value: "15" },
  })
  fireEvent.click(screen.getByRole("checkbox"))
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: " A " },
  })
  expect(load).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  expect(load.mock.calls[1][0]).toMatchObject({
    supplier: "工厂甲",
    window_days: 15,
    deduct_transit: true,
    query: "A",
    page: 1,
  })
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled()
  )
  fireEvent.change(screen.getByLabelText("商品搜索"), {
    target: { value: "draft" },
  })
  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  expect(load.mock.calls[2][0]).toMatchObject({
    query: "A",
    supplier: "工厂甲",
    page: 2,
  })
})

test("saves supplier-wide MOQ in the committed brand and keeps inputs after a save conflict", async () => {
  render(<ReplenishmentPage />)
  await screen.findByText("A")
  fireEvent.change(screen.getByLabelText("品牌"), {
    target: { value: "cbanner_womens" },
  })
  fireEvent.click(screen.getByRole("button", { name: "设置补货规则" }))
  const dialog = within(screen.getByRole("dialog"))
  await dialog.findByLabelText("供应商交期")
  expect(dialog.getByText(/千百度男鞋 · 工厂甲/)).toBeInTheDocument()
  fireEvent.change(dialog.getByLabelText("供应商交期"), {
    target: { value: "10" },
  })
  fireEvent.change(dialog.getByLabelText("供应商合计起订量"), {
    target: { value: "100" },
  })
  fireEvent.change(dialog.getByLabelText("女鞋 35 配比"), {
    target: { value: "1" },
  })
  fireEvent.change(dialog.getByLabelText("女鞋 36 配比"), {
    target: { value: "2" },
  })
  save.mockRejectedValueOnce(new Error("供应商规则已被其他页面修改"))
  fireEvent.click(dialog.getByRole("button", { name: "保存规则" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "规则已被其他页面修改"
  )
  expect(dialog.getByLabelText("供应商合计起订量")).toHaveValue(100)
  expect(save).toHaveBeenCalledWith({
    brand: "cbanner_mens",
    supplier: "工厂甲",
    lead_days: 10,
    min_order_qty: 100,
    cover_days: 14,
    size_ratios: { 女鞋: { "35": 1, "36": 2 } },
    version: 0,
  })
  fireEvent.click(dialog.getByRole("button", { name: "保存规则" }))
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  )
  expect(load).toHaveBeenCalledTimes(2)
})

test("does not silently save an all-zero size ratio group", async () => {
  render(<ReplenishmentPage />)
  await screen.findByText("A")
  fireEvent.click(screen.getByRole("button", { name: "设置补货规则" }))
  const dialog = within(screen.getByRole("dialog"))
  await dialog.findByLabelText("供应商交期")
  fireEvent.change(dialog.getByLabelText("供应商交期"), {
    target: { value: "10" },
  })
  fireEvent.change(dialog.getByLabelText("供应商合计起订量"), {
    target: { value: "100" },
  })
  fireEvent.change(dialog.getByLabelText("女鞋 35 配比"), {
    target: { value: "0" },
  })
  fireEvent.click(dialog.getByRole("button", { name: "保存规则" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "至少填写一个大于 0"
  )
  expect(save).not.toHaveBeenCalled()
})

test("view-only access hides edits and missing sources show unknown statistics", async () => {
  permission.manage = false
  load.mockResolvedValue({ ...response(), items: [], ready: false })
  render(<ReplenishmentPage />)
  await screen.findByText("数据源未就绪，请先补齐库存及日销")
  expect(
    screen.queryByRole("button", { name: /设置.*规则/ })
  ).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: /需要补货/ })).toHaveTextContent(
    "—"
  )
})

test("cancels superseded queries and ignores late results", async () => {
  render(<ReplenishmentPage />)
  await screen.findByText("A")
  let resolve!: (value: ReplenishmentResponse) => void
  load.mockReturnValueOnce(
    new Promise<ReplenishmentResponse>((done) => {
      resolve = done
    })
  )
  fireEvent.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2))
  const signal = load.mock.calls[1][1].signal as AbortSignal
  expect(load.mock.calls[1][1].refresh).toBe(true)
  fireEvent.click(screen.getByRole("button", { name: /数据或规则待完善/ }))
  await waitFor(() => expect(load).toHaveBeenCalledTimes(3))
  expect(signal.aborted).toBe(true)
  await act(async () => resolve({ ...response(), total: 999 }))
  expect(screen.queryByText(/共 999 项/)).not.toBeInTheDocument()
})
