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
import type { OverviewResponse } from "@/lib/stock-overview"
import { StockOverviewPage } from "./stock-overview-page"

const { overview, week, options, assign, assignees, auth } = vi.hoisted(() => ({
  overview: vi.fn(),
  week: vi.fn(),
  options: vi.fn(),
  assign: vi.fn(),
  assignees: vi.fn(),
  auth: { manager: true },
}))
vi.mock("@/lib/api", () => ({
  getStockOverview: overview,
  getStockOverviewWeek: week,
  getStockAlertOptions: options,
  createOverviewTask: assign,
  getStockAlertAssignees: assignees,
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({
    user: { id: 7, permissions: ["product.view"] },
    hasPermission: (permission: string) =>
      permission === "product.view" || auth.manager,
  }),
}))

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

test("an operator can inspect sizes and confirm the exact decision snapshot in the existing workflow", async () => {
  render(<StockOverviewPage />)
  fireEvent.click(await screen.findByRole("button", { name: "STOCK-42" }))
  const detail = screen.getByRole("dialog")
  expect(within(detail).getByText("牛皮")).toBeInTheDocument()
  expect(
    within(detail).getByRole("cell", { name: "200 双" })
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
    screen.queryByRole("button", { name: "分配待办" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "退出规则" })
  ).not.toBeInTheDocument()
})
