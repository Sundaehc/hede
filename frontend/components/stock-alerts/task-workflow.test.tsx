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
import { StockAlertTaskDialog, CreateStockAlertTaskDialog } from "./task-dialog"
import { StockAlertTaskReminder } from "./task-reminder"
import { StockAlertTasksPage } from "./tasks-page"
import { StockAlertsPage } from "./stock-alerts-page"
import { BatchTaskDialog } from "./batch-task-dialog"
import { publishBusinessDataChange } from "@/lib/business-data-sync"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import { clearStockModuleQueries } from "@/lib/stock-module-query"
import type { StockAlertItem } from "@/lib/stock-alerts"
import type { StockAlertTask } from "@/lib/stock-alert-tasks"

const mock = vi.hoisted(() => ({
  detail: vi.fn(),
  events: vi.fn(),
  update: vi.fn(),
  create: vi.fn(),
  assignees: vi.fn(),
  reminders: vi.fn(),
  list: vi.fn(),
  options: vi.fn(),
  batchCreate: vi.fn(),
  batchUpdate: vi.fn(),
  alerts: vi.fn(),
  auth: { id: 2, manager: false },
  search: { value: "" },
}))
vi.mock("@/lib/api", () => ({
  getStockAlertTask: mock.detail,
  getStockAlertTaskEvents: mock.events,
  updateStockAlertTask: mock.update,
  createStockAlertTask: mock.create,
  getStockAlertAssignees: mock.assignees,
  getStockAlertTaskReminders: mock.reminders,
  getStockAlertTasks: mock.list,
  getStockAlertOptions: mock.options,
  createStockAlertTasks: mock.batchCreate,
  updateStockAlertTasks: mock.batchUpdate,
  getStockAlerts: mock.alerts,
}))
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(mock.search.value),
}))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({
    user: { id: mock.auth.id },
    hasPermission: (permission: string) =>
      permission === "product.view" || mock.auth.manager,
  }),
}))

const source: StockAlertItem = {
  id: 11,
  brand: "demo",
  sku: "DEMO-001",
  original_sku: "OLD-01",
  product_name: "样品鞋",
  color: "黑色",
  year: "2026",
  season: "冬",
  launch_date: "2026-08-01",
  listed_days: 80,
  first_inbound_date: "2026-08-01",
  last_inbound_date: "2026-09-01",
  last_sales_date: null,
  available_quantity: "100",
  purchase_received_reference: "100",
  gross_sales: "0",
  net_sales: "0",
  sales_returns: "0",
  sell_through_rate: "0",
  sales_issues: [],
  inbound_issues: [],
  warning: true,
  pending_reasons: [],
  rule_age_days: 60,
  rule_rate: "20",
  rule_source: "default",
}
function task(values: Partial<StockAlertTask> = {}): StockAlertTask {
  return {
    id: 1,
    brand: "demo",
    product_id: 11,
    kind: "slow",
    sku: source.sku,
    original_sku: source.original_sku,
    product_name: source.product_name,
    color: source.color,
    snapshot: { ...source, stock_date: "2026-11-13", sales_end: "2026-11-12" },
    assignee_id: 2,
    assignee_name: "负责人乙",
    due_date: "2026-11-12",
    overdue: true,
    status: "pending",
    measures: "",
    result: "",
    version: 1,
    created_at: "2026-11-10T00:00:00Z",
    updated_at: "2026-11-10T00:00:00Z",
    completed_at: null,
    ...values,
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  clearSessionQueryStates()
  clearStockModuleQueries()
  window.localStorage.clear()
  mock.auth.id = 2
  mock.auth.manager = false
  mock.search.value = ""
  mock.detail.mockResolvedValue({ item: task() })
  mock.events.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  mock.assignees.mockResolvedValue({
    items: [
      { id: 2, name: "负责人乙", department: "商品部" },
      { id: 3, name: "负责人丙", department: "运营部" },
    ],
  })
  mock.options.mockResolvedValue({
    brands: [{ value: "demo", label: "示例品牌" }],
  })
  mock.reminders.mockResolvedValue({ open: 1, overdue: 1, today: "2026-11-14" })
  mock.list.mockResolvedValue({
    items: [task()],
    total: 1,
    page: 1,
    page_size: 25,
    counts: { open: 1, overdue: 1, completed: 0 },
    today: "2026-11-14",
  })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

test("owner records progress, keeps drafts on a concurrent change, and completes with measures and result", async () => {
  render(<StockAlertTaskDialog id={1} onClose={vi.fn()} />)
  await screen.findByRole("button", { name: "完成待办" })
  const dialog = within(
    await screen.findByRole("dialog", { name: /预警待办 #1/ })
  )
  expect(dialog.queryByLabelText("处理期限")).not.toBeInTheDocument()
  expect(mock.assignees).not.toHaveBeenCalled()
  fireEvent.click(dialog.getByRole("button", { name: "完成待办" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent("完成前请填写")
  expect(mock.update).not.toHaveBeenCalled()
  fireEvent.change(dialog.getByLabelText("处理措施"), {
    target: { value: "协调调拨" },
  })
  fireEvent.change(dialog.getByLabelText("处理结果"), {
    target: { value: "已完成" },
  })
  mock.update.mockRejectedValueOnce(
    new Error("待办已被其他页面修改，请重新打开")
  )
  fireEvent.click(dialog.getByRole("button", { name: "保存进度" }))
  await waitFor(() =>
    expect(dialog.getByRole("alert")).toHaveTextContent("其他页面修改")
  )
  expect(dialog.getByLabelText("处理措施")).toHaveValue("协调调拨")
  expect(mock.update.mock.calls[0][1]).toEqual({
    version: 1,
    status: "pending",
    measures: "协调调拨",
    result: "已完成",
  })
  mock.update.mockResolvedValueOnce({
    item: task({
      status: "completed",
      version: 2,
      overdue: false,
      measures: "协调调拨",
      result: "已完成",
      completed_at: "2026-11-14T08:00:00Z",
    }),
  })
  fireEvent.click(dialog.getByRole("button", { name: "完成待办" }))
  await waitFor(() =>
    expect(screen.getByText(/已停止提醒/)).toBeInTheDocument()
  )
  expect(mock.update.mock.calls[1][1].status).toBe("completed")
  expect(
    screen.queryByRole("button", { name: "完成待办" })
  ).not.toBeInTheDocument()
})

test("viewers cannot edit another user's task", async () => {
  mock.auth.id = 3
  render(<StockAlertTaskDialog id={1} onClose={vi.fn()} />)
  expect(await screen.findByLabelText("处理措施")).toBeDisabled()
  expect(
    screen.queryByRole("button", { name: "保存进度" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "完成待办" })
  ).not.toBeInTheDocument()
})

test("manager can assign a task with a deadline and see duplicate errors without losing the draft", async () => {
  mock.auth.manager = true
  mock.create.mockRejectedValueOnce(new Error("该商品已有未完成待办（#9）"))
  render(
    <CreateStockAlertTaskDialog
      item={source}
      kind="slow"
      brandLabel="示例品牌"
      onClose={vi.fn()}
      onCreated={vi.fn()}
    />
  )
  const dialog = within(screen.getByRole("dialog"))
  await waitFor(() =>
    expect(dialog.getByRole("button", { name: "确认分配" })).toBeEnabled()
  )
  fireEvent.change(dialog.getByLabelText("处理措施"), {
    target: { value: "核查上架" },
  })
  fireEvent.click(dialog.getByRole("button", { name: "确认分配" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent("已有未完成待办")
  expect(dialog.getByLabelText("处理措施")).toHaveValue("核查上架")
  expect(mock.create).toHaveBeenCalledWith(
    expect.objectContaining({
      brand: "demo",
      product_id: 11,
      kind: "slow",
      assignee_id: 2,
      measures: "核查上架",
    })
  )
})

test("reminders update after a local save and disappear after completion", async () => {
  render(<StockAlertTaskReminder />)
  const link = await screen.findByRole("link", { name: /已超期 1 项/ })
  expect(link).toHaveAttribute("href", "/stock-alerts/tasks?view=mine-open")
  mock.reminders.mockResolvedValueOnce({
    open: 0,
    overdue: 0,
    today: "2026-11-14",
  })
  act(() => publishBusinessDataChange(["stock-alert-tasks"]))
  await waitFor(() =>
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  )
})

test("list submits drafts explicitly and keeps existing rows visible during refresh", async () => {
  render(<StockAlertTasksPage />)
  await screen.findByText("DEMO-001")
  fireEvent.change(screen.getByLabelText("搜索待办"), {
    target: { value: " OLD " },
  })
  expect(mock.list).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(2))
  expect(mock.list.mock.calls[1][0]).toMatchObject({
    query: "OLD",
    page: 1,
    scope: "mine",
  })
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  )
  let resolve!: (value: unknown) => void
  mock.list.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  fireEvent.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(mock.list).toHaveBeenCalledTimes(3))
  expect(screen.getByText("DEMO-001")).toBeInTheDocument()
  await act(async () =>
    resolve({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
      counts: { open: 0, overdue: 0, completed: 0 },
      today: "2026-11-14",
    })
  )
  await screen.findByText("当前筛选下没有待办")
})

test("reminders refresh each minute while visible and pause polling while hidden", async () => {
  vi.useFakeTimers()
  render(<StockAlertTaskReminder />)
  await act(async () => {
    await Promise.resolve()
  })
  expect(screen.getByRole("link", { name: /已超期 1 项/ })).toBeInTheDocument()
  const initialCalls = mock.reminders.mock.calls.length
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000)
  })
  expect(mock.reminders.mock.calls.length).toBe(initialCalls + 1)
  const visibility = vi
    .spyOn(document, "visibilityState", "get")
    .mockReturnValue("hidden")
  await act(async () => {
    await vi.advanceTimersByTimeAsync(120_000)
  })
  expect(mock.reminders.mock.calls.length).toBe(initialCalls + 1)
  visibility.mockReturnValue("visible")
  act(() => document.dispatchEvent(new Event("visibilitychange")))
  await act(async () => {
    await Promise.resolve()
  })
  expect(mock.reminders.mock.calls.length).toBe(initialCalls + 2)
  visibility.mockRestore()
})

test("selects tasks across pages, completes in bulk with explicit shared content and retains failed selections", async () => {
  mock.list.mockImplementation(async (filters) => ({
    items: [
      task({
        id: filters.page,
        sku: `DEMO-${filters.page}`,
        version: filters.page + 2,
      }),
    ],
    total: 50,
    page: filters.page,
    page_size: 25,
    counts: { open: 50, overdue: 50, completed: 0 },
    today: "2026-11-14",
  }))
  mock.batchUpdate.mockResolvedValue({
    total: 2,
    succeeded: [1],
    failed: [{ id: 2, label: "DEMO-2", reason: "版本已变更，请重新选择" }],
  })
  render(<StockAlertTasksPage />)
  fireEvent.click(
    await screen.findByRole("checkbox", { name: "选择 DEMO-1（#1）" })
  )
  fireEvent.click(screen.getByRole("button", { name: "下一页" }))
  fireEvent.click(
    await screen.findByRole("checkbox", { name: "选择 DEMO-2（#2）" })
  )
  expect(screen.getByText("已选 2 项")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "批量处理" }))
  const dialog = within(
    await screen.findByRole("dialog", { name: "批量处理待办" })
  )
  fireEvent.change(dialog.getByLabelText("统一处理状态"), {
    target: { value: "completed" },
  })
  fireEvent.click(dialog.getByLabelText("填写统一处理措施"))
  fireEvent.click(dialog.getByLabelText("填写统一处理结果"))
  fireEvent.click(dialog.getByRole("button", { name: "确认完成 2 项" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent("不能为空")
  expect(mock.batchUpdate).not.toHaveBeenCalled()
  fireEvent.change(dialog.getByLabelText("统一处理措施"), {
    target: { value: "统一调拨" },
  })
  fireEvent.change(dialog.getByLabelText("统一处理结果"), {
    target: { value: "调拨完成" },
  })
  fireEvent.click(dialog.getByRole("button", { name: "确认完成 2 项" }))
  expect(
    await dialog.findByText("操作完成：成功 1 项，失败 1 项")
  ).toBeInTheDocument()
  expect(mock.batchUpdate).toHaveBeenCalledWith({
    items: [
      { id: 1, version: 3 },
      { id: 2, version: 4 },
    ],
    changes: { status: "completed", measures: "统一调拨", result: "调拨完成" },
  })
  expect(screen.getByText("已选 1 项")).toBeInTheDocument()
  expect(dialog.getByText(/版本已变更/)).toBeInTheDocument()
  fireEvent.click(dialog.getByRole("button", { name: "关闭" }))
  fireEvent.change(screen.getByLabelText("搜索待办"), {
    target: { value: "new" },
  })
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  expect(screen.getByText("已选 0 项")).toBeInTheDocument()
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  )
})

test("batch assignment changes only the supplied assignment field", async () => {
  mock.auth.manager = true
  mock.batchUpdate.mockResolvedValue({ total: 1, succeeded: [1], failed: [] })
  render(
    <BatchTaskDialog
      mode="assign"
      items={[task()]}
      onClose={vi.fn()}
      onApplied={vi.fn()}
    />
  )
  const dialog = within(
    await screen.findByRole("dialog", { name: "批量调整分配" })
  )
  await dialog.findByRole("option", { name: "负责人丙 · 运营部" })
  fireEvent.change(dialog.getByLabelText("统一负责人"), {
    target: { value: "3" },
  })
  fireEvent.click(dialog.getByRole("button", { name: "确认操作 1 项" }))
  await dialog.findByText("操作完成：成功 1 项，失败 0 项")
  expect(mock.batchUpdate).toHaveBeenCalledWith({
    items: [{ id: 1, version: 1 }],
    changes: { assignee_id: 3 },
  })
})

test("warning list selects eligible products and reports partial batch assignment failures", async () => {
  mock.auth.manager = true
  mock.alerts.mockResolvedValue({
    items: [
      { ...source, brand: "cbanner_mens" },
      { ...source, id: 12, sku: "DEMO-002", brand: "cbanner_mens" },
      {
        ...source,
        id: 13,
        sku: "ASSIGNED",
        task: {
          id: 9,
          status: "pending",
          assignee_name: "负责人乙",
          due_date: "2026-11-30",
          overdue: false,
        },
      },
    ],
    total: 3,
    page: 1,
    page_size: 25,
    counts: { warning: 3, pending: 0 },
    warning_stock: "300",
    stock_products: 3,
    seasons: [],
    stock_date: "2026-11-13",
    sales_end: "2026-11-12",
    source_issues: [],
    unmatched_stock_rows: 0,
    ready: true,
    rule: { age_days: 15, rate: "20", version: 0, source: "default" },
  })
  mock.batchCreate.mockResolvedValue({
    total: 2,
    succeeded: [11],
    failed: [{ id: 12, label: "DEMO-002", reason: "已有未完成待办" }],
  })
  render(<StockAlertsPage kind="zero" />)
  const selectAll = await screen.findByRole("checkbox", {
    name: "选择本页可分配商品",
  })
  await waitFor(() => expect(selectAll).toBeEnabled())
  expect(
    screen.getByRole("checkbox", { name: "选择 ASSIGNED（#13）" })
  ).toBeDisabled()
  fireEvent.click(selectAll)
  expect(screen.getByText("已选 2 项")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "批量分配待办" }))
  const dialog = within(
    await screen.findByRole("dialog", { name: "批量分配待办" })
  )
  await dialog.findByRole("option", { name: "负责人乙 · 商品部" })
  fireEvent.change(dialog.getByLabelText("统一负责人"), {
    target: { value: "2" },
  })
  fireEvent.click(dialog.getByRole("button", { name: "确认操作 2 项" }))
  await dialog.findByText("操作完成：成功 1 项，失败 1 项")
  expect(mock.batchCreate).toHaveBeenCalledWith(
    expect.objectContaining({
      brand: "cbanner_mens",
      kind: "zero",
      product_ids: [11, 12],
      assignee_id: 2,
    })
  )
  expect(screen.getByText("已选 1 项")).toBeInTheDocument()
})
