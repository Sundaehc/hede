import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import { clearStockModuleQueries } from "@/lib/stock-module-query"
import { beijingDate } from "@/lib/stock-alert-tasks"
import type { OverviewItem, OverviewResponse } from "@/lib/stock-overview"
import type { PortfolioResponse } from "@/lib/stock-portfolio"
import { StockOverviewPage } from "./stock-overview-page"

const {
  overview,
  week,
  options,
  assign,
  batchAssign,
  assignees,
  portfolio,
  portfolioItem,
  saveClearance,
  getArrivals,
  getClearanceWeek,
  saveRecovery,
  auth,
} = vi.hoisted(() => ({
  overview: vi.fn(),
  week: vi.fn(),
  options: vi.fn(),
  assign: vi.fn(),
  batchAssign: vi.fn(),
  assignees: vi.fn(),
  portfolio: vi.fn(),
  portfolioItem: vi.fn(),
  saveClearance: vi.fn(),
  getArrivals: vi.fn(),
  getClearanceWeek: vi.fn(),
  saveRecovery: vi.fn(),
  auth: { manager: true },
}))
vi.mock("@/lib/api", () => ({
  getStockOverview: overview,
  getStockOverviewWeek: week,
  getStockAlertOptions: options,
  createOverviewTask: assign,
  createOverviewTasks: batchAssign,
  getStockAlertAssignees: assignees,
  getStockPortfolio: portfolio,
  getStockPortfolioItem: portfolioItem,
  saveStockClearance: saveClearance,
  getStockArrivalBoard: getArrivals,
  getStockClearanceWeek: getClearanceWeek,
  saveStockClearanceRecovery: saveRecovery,
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({
    user: { id: 7, permissions: ["product.view"] },
    hasPermission: (permission: string) =>
      permission === "product.view" || auth.manager,
  }),
}))

const portfolioResponse: PortfolioResponse = {
  items: [
    {
      product_id: 12,
      sku: "ORIGINAL-12",
      product_name: "试点单鞋",
      children: 2,
      available_quantity: 18,
      confirmed_clearance_quantity: 0,
      statuses: ["selling"],
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  totals: { selling: 18 },
  years: ["2026"],
  seasons: ["春", "秋"],
  categories: ["单鞋"],
  sell_through: null,
  sell_through_covered: 0,
  sources: {
    stock_date: "2099-01-01",
    aligned: true,
    unmatched_stock_rows: 0,
  },
}

test("keeps portfolio options and the table in place while loading a new filter", async () => {
  let resolveFiltered!: (response: PortfolioResponse) => void
  const filtered = new Promise<PortfolioResponse>((resolve) => {
    resolveFiltered = resolve
  })
  portfolio
    .mockResolvedValueOnce(portfolioResponse)
    .mockReturnValueOnce(filtered)
  render(<StockOverviewPage />)
  const results = await screen.findByRole("region", { name: "库存货盘结果" })
  const table = within(results).getByRole("table")
  const season = screen.getByLabelText("销售季节")
  fireEvent.change(season, { target: { value: "秋" } })

  expect(season).toHaveValue("秋")
  expect(within(season).getByRole("option", { name: "春" })).toBeInTheDocument()
  expect(within(results).getByRole("table")).toBe(table)
  expect(
    within(table).getByRole("button", { name: "ORIGINAL-12" })
  ).toBeDisabled()
  expect(results).toHaveAttribute("aria-busy", "true")
  expect(screen.getByText("正在更新…")).toBeVisible()

  resolveFiltered({
    ...portfolioResponse,
    items: [
      { ...portfolioResponse.items[0], product_id: 13, sku: "ORIGINAL-13" },
    ],
  })
  expect(
    await within(table).findByRole("button", { name: "ORIGINAL-13" })
  ).toBeEnabled()
  expect(
    within(table).queryByRole("button", { name: "ORIGINAL-12" })
  ).not.toBeInTheDocument()
  expect(results).toHaveAttribute("aria-busy", "false")
})

test("opens an original-code family on demand and saves clearance for only the chosen child", async () => {
  portfolio.mockResolvedValue(portfolioResponse)
  const child = {
    sku: "CHILD-12",
    id: 12,
    original_sku: "ORIGINAL-12",
    product_name: "试点单鞋",
    launch_date: "2098-11-01",
    available_quantity: 10,
    purchase_in_transit: 0,
    stock: [],
    clearance: null,
  }
  portfolioItem.mockResolvedValue({
    original_sku: "ORIGINAL-12",
    stock_date: "2099-01-01",
    unmatched_stock: 0,
    items: [
      child,
      { ...child, sku: "CHILD-13", id: 13, available_quantity: 8 },
    ],
    receipts: null,
    orders: null,
    sales: { cutoff: "2098-12-31", windows: {}, channels: [] },
  })
  saveClearance.mockResolvedValue({
    message: "已确认清仓",
    item: {
      confirmed: true,
      version: 1,
      reason: "运营确认退出",
      updated_at: "2099-01-01T00:00:00Z",
      updated_by: 7,
    },
  })
  render(<StockOverviewPage />)
  expect(portfolioItem).not.toHaveBeenCalled()
  await screen.findByRole("option", { name: "秋" })
  fireEvent.change(screen.getByLabelText("销售季节"), {
    target: { value: "秋" },
  })
  await waitFor(() =>
    expect(portfolio).toHaveBeenLastCalledWith(
      "cbanner_womens",
      expect.objectContaining({ season: "秋" }),
      expect.any(AbortSignal),
      false
    )
  )
  fireEvent.click(await screen.findByRole("button", { name: "ORIGINAL-12" }))
  const dialog = await screen.findByRole("dialog", { name: "ORIGINAL-12" })
  expect(within(dialog).getByText("CHILD-13")).toBeVisible()
  fireEvent.click(
    within(dialog).getAllByRole("button", { name: "确认清仓" })[0]
  )
  fireEvent.change(within(dialog).getByLabelText("处理原因"), {
    target: { value: "运营确认退出" },
  })
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() =>
    expect(saveClearance).toHaveBeenCalledWith(
      "cbanner_womens",
      12,
      true,
      "运营确认退出",
      0
    )
  )
  expect(
    await within(dialog).findByRole("button", { name: "解除清仓" })
  ).toBeVisible()
  expect(
    within(dialog).getAllByRole("button", { name: "确认清仓" })
  ).toHaveLength(1)
})

const response: OverviewResponse = {
  inventory: {
    available: 1000,
    total_30: 500,
    coverage_days: 60,
    regular_7: 72,
    regular_30: 300,
    clearance_7: 50,
    clearance_30: 200,
    buckets: [{ key: "clearance", units: 1000, styles: 1 }],
  },
  sources: {
    stock_date: "2099-01-01",
    sales_end: "2098-12-31",
    aligned: true,
    history_aligned: true,
    scope_complete: true,
    unmatched_stock_rows: 10,
  },
  scopes: [{ year: "2024", season: "冬" }],
  policies: [],
  counts: { zero: 0, slow: 0, clearance: 1, replenish: 0, review: 0 },
  assignable: 1,
  in_progress: 0,
  page: 1,
  page_size: 25,
  total: 1,
  today: "2099-01-01",
  items: [
    {
      id: 42,
      brand: "cbanner_womens",
      kind: "clearance",
      sku: "STOCK-42",
      product_name: "冬靴",
      color: "黑色",
      original_sku: null,
      year: "2024",
      season: "冬",
      upper_material: "牛皮",
      launch_date: "2024-10-01",
      first_inbound_date: null,
      last_inbound_date: null,
      exit_date: "2099-01-09",
      sell_through_rate: "90.00",
      regular_7: 72,
      regular_30: 300,
      clearance_7: 50,
      clearance_30: 200,
      available_quantity: 1000,
      reason: "预计正常净销 300 双",
      sizes: [{ name: "40", available: 350, quantity: 200 }],
      size_inventory: [
        { name: "40", available: 350, core: false, in_action: true },
      ],
      channel: "达播清仓",
      quantity: 200,
      task: null,
      signature: "a".repeat(64),
      due_date: "2099-01-09",
    },
  ],
}

beforeEach(() => {
  portfolio.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
    totals: {},
    years: [],
    seasons: [],
    categories: [],
    sources: { stock_date: null, aligned: false, unmatched_stock_rows: 0 },
  })
  vi.resetAllMocks()
  clearSessionQueryStates()
  clearStockModuleQueries()
  auth.manager = true
  overview.mockResolvedValue(response)
  options.mockResolvedValue({
    brands: [{ value: "cbanner_womens", label: "千百度女鞋" }],
  })
  week.mockResolvedValue({
    start: "2098-12-22",
    end: "2098-12-28",
    created: 2,
    completed: 1,
    overdue: 0,
    completed_styles: 1,
    net_sales: null,
    clearance_net_sales: null,
    stock_change: null,
    recovery_amount: null,
  })
  assignees.mockResolvedValue({
    items: [{ id: 7, name: "王伟", department: "运营" }],
  })
  assign.mockResolvedValue({ item: { id: 55, assignee_name: "王伟" } })
})
afterEach(cleanup)

test("loads arrival and clearance tabs on demand and preserves decimal input when confirming recovery", async () => {
  getArrivals.mockResolvedValue({
    items: [],
    today: "2098-12-29",
    through: "2098-12-31",
    source_ready: true,
    total: 0,
    page: 1,
    page_size: 25,
  })
  getClearanceWeek.mockResolvedValue({
    end: "2098-12-28",
    can_confirm: true,
    clearance_products: 1,
    stock_covered: 0,
    recovery_amount: null,
    recovery_covered: 0,
    items: [
      {
        product_id: 42,
        sku: "CLEAR-42",
        net_sales: 7,
        ending_stock: null,
        recovery: null,
      },
    ],
  })
  saveRecovery.mockResolvedValue({ message: "回收金额已确认" })
  render(<StockOverviewPage />)
  expect(getClearanceWeek).not.toHaveBeenCalled()
  expect(getArrivals).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "到货清单" }))
  let dialog = await screen.findByRole("dialog", { name: "到货清单" })
  expect(
    await within(dialog).findByText(/2098-12-29 至 2098-12-31/)
  ).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole("button", { name: "约定超期" }))
  await waitFor(() =>
    expect(getArrivals).toHaveBeenLastCalledWith(
      "cbanner_womens",
      "overdue",
      1,
      expect.any(AbortSignal)
    )
  )
  fireEvent.keyDown(dialog, { key: "Escape" })
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "到货清单" })
    ).not.toBeInTheDocument()
  )

  fireEvent.click(await screen.findByRole("button", { name: "清货明细" }))
  dialog = await screen.findByRole("dialog", { name: "清货周复盘" })
  fireEvent.click(
    await within(dialog).findByRole("button", { name: "录入金额" })
  )
  fireEvent.change(within(dialog).getByLabelText("确认回收金额（元）"), {
    target: { value: "99999999999999.99" },
  })
  fireEvent.change(within(dialog).getByLabelText("结算凭证或备注"), {
    target: { value: "复盘凭证" },
  })
  fireEvent.click(within(dialog).getByRole("button", { name: "确认金额" }))
  await waitFor(() =>
    expect(saveRecovery).toHaveBeenCalledWith(
      "cbanner_womens",
      "2098-12-22",
      42,
      { amount: "99999999999999.99", reference: "复盘凭证" }
    )
  )
  await waitFor(() => expect(week).toHaveBeenCalledTimes(2))
})

test("an operator can inspect sizes and confirm the exact decision snapshot in the existing workflow", async () => {
  render(<StockOverviewPage />)
  fireEvent.click(await screen.findByRole("button", { name: "STOCK-42" }))
  const detail = screen.getByRole("dialog")
  expect(within(detail).getByText("牛皮")).toBeInTheDocument()
  expect(
    within(
      within(detail).getByRole("table", { name: "尺码库存及处理建议" })
    ).getByRole("cell", { name: "200 双" })
  ).toBeInTheDocument()
  fireEvent.click(within(detail).getByRole("button", { name: "分配待办" }))
  const dialog = await screen.findByRole("dialog", { name: "分配预警待办" })
  await waitFor(() =>
    expect(within(dialog).getByLabelText("负责人")).toHaveValue("7")
  )
  const submit = within(dialog)
    .getAllByRole("button")
    .find((button) => button.getAttribute("type") === "submit")!
  fireEvent.click(submit)
  await waitFor(() =>
    expect(assign).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "clearance",
        product_id: 42,
        due_date: "2099-01-09",
        signature: "a".repeat(64),
        assignee_id: 7,
      })
    )
  )
  expect(await screen.findByText(/已分配待办 #55/)).toBeInTheDocument()
})

test("view-only users can inspect the same evidence but cannot assign or edit rules", async () => {
  auth.manager = false
  render(<StockOverviewPage />)
  fireEvent.click(await screen.findByRole("button", { name: "查看依据" }))
  expect(screen.getByRole("dialog")).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "批量分配待办", hidden: true })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "分配待办" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "退出规则" })
  ).not.toBeInTheDocument()
})

test("assigns multiple recommendation types across pages and keeps only failures selected", async () => {
  const deadline = beijingDate(1)
  const clearance: OverviewItem = { ...response.items[0]!, due_date: deadline }
  const zero: OverviewItem = {
    ...clearance,
    kind: "zero",
    due_date: null,
    signature: "b".repeat(64),
  }
  const review: OverviewItem = {
    ...clearance,
    id: 43,
    sku: "STOCK-43",
    kind: "review",
    signature: null,
  }
  overview.mockImplementation(async ({ page }) => ({
    ...response,
    page,
    page_size: 2,
    total: 3,
    items: page === 1 ? [clearance, review] : [zero],
    counts: { ...response.counts, zero: 1, review: 1 },
  }))
  const reason = "建议依据已变化，请刷新并重新勾选后再分配"
  batchAssign.mockResolvedValue({
    total: 2,
    succeeded: ["42/clearance"],
    failed: [{ id: "42/zero", label: "STOCK-42", reason }],
  })

  render(<StockOverviewPage />)
  const selectPage = await screen.findByRole("checkbox", {
    name: "选择本页可分配建议",
  })
  expect(
    screen.queryByRole("checkbox", { name: /STOCK-43/ })
  ).not.toBeInTheDocument()
  fireEvent.click(selectPage)
  expect(
    screen.getByRole("checkbox", { name: /STOCK-42.*清货跟进/ })
  ).toBeChecked()
  expect(screen.getByText("已选 1 项")).toBeInTheDocument()

  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  const zeroChoice = await screen.findByRole("checkbox", {
    name: /STOCK-42.*新品零动销/,
  })
  expect(zeroChoice).not.toBeChecked()
  fireEvent.click(zeroChoice)
  expect(screen.getByText("已选 2 项")).toBeInTheDocument()

  fireEvent.click(screen.getByRole("button", { name: "批量分配待办" }))
  const dialog = within(
    await screen.findByRole("dialog", { name: "批量分配待办" })
  )
  expect(dialog.getByLabelText("统一处理期限")).toHaveAttribute("max", deadline)
  expect(dialog.getByLabelText("统一处理期限")).toHaveValue(deadline)
  await dialog.findByRole("option", { name: /王伟/ })
  fireEvent.change(dialog.getByLabelText("统一负责人"), {
    target: { value: "7" },
  })
  fireEvent.click(dialog.getByRole("button", { name: "确认操作 2 项" }))
  expect(await dialog.findByRole("status")).toHaveTextContent(
    "操作完成：成功 1 项，失败 1 项"
  )
  expect(
    dialog.getByText(`STOCK-42 · 新品零动销：${reason}`)
  ).toBeInTheDocument()
  expect(batchAssign).toHaveBeenCalledExactlyOnceWith({
    brand: clearance.brand,
    assignee_id: 7,
    due_date: deadline,
    measures: "",
    items: [
      { product_id: 42, kind: "clearance", signature: clearance.signature },
      { product_id: 42, kind: "zero", signature: zero.signature },
    ],
  })
  fireEvent.click(dialog.getByRole("button", { name: "关闭" }))
  expect(screen.getByText("已选 1 项")).toBeInTheDocument()
  expect(
    screen.getByRole("checkbox", { name: /STOCK-42.*新品零动销/ })
  ).toBeChecked()
  fireEvent.click(screen.getByRole("button", { name: /清货跟进/ }))
  expect(await screen.findByText("已选 0 项")).toBeInTheDocument()
})
