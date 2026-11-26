import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, afterEach, expect, test, vi } from "vitest"
import SuppliersPage from "@/app/suppliers/page"
import { SupplierLedgerPage } from "./supplier-ledger-page"
import { CounterpartyLedgerDialog } from "./counterparty-ledger-dialog"
import { SessionQueryProvider } from "@/lib/session-query-state"
import { PageTabs } from "@/components/auth/page-tabs"
import { defaultLedgerQuery } from "@/lib/supplier-ledger-tabs"
import { publishBusinessDataChange } from "@/lib/business-data-sync"
import { clearStockModuleQueries } from "@/lib/stock-module-cache"
import type { CounterpartyLedgerResponse } from "@/lib/api"

const { api, navigation, auth } = vi.hoisted(() => ({
  api: {
    listSuppliers: vi.fn(),
    listSupplierBrands: vi.fn(),
    getSupplier: vi.fn(),
    listCounterpartyLedger: vi.fn(),
    downloadCounterpartyLedger: vi.fn(),
    downloadGeneralCustomerLedger: vi.fn(),
    getPinnedPageTabs: vi.fn(),
  },
  navigation: { pathname: "/suppliers", push: vi.fn() },
  auth: {
    user: { id: 1, role_code: "super_admin", department_code: "财务部" },
    hasPermission: vi.fn(),
  },
}))
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: navigation.push }),
  usePathname: () => navigation.pathname,
}))
vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => auth }))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  ...api,
}))
vi.mock("@/components/ui/date-range-control", () => ({
  DateRangeControl: ({
    start,
    end,
    onStartChange,
    onEndChange,
    actions,
  }: {
    start: string
    end: string
    onStartChange: (value: string) => void
    onEndChange: (value: string) => void
    actions?: import("react").ReactNode
  }) => (
    <>
      <input
        aria-label="起始日期"
        value={start}
        onChange={(event) => onStartChange(event.target.value)}
      />
      <input
        aria-label="截止日期"
        value={end}
        onChange={(event) => onEndChange(event.target.value)}
      />
      <button
        type="button"
        onClick={() => {
          onStartChange("2025-01-01")
          onEndChange("2026-08-31")
        }}
      >
        设定测试区间
      </button>
      {actions}
    </>
  ),
}))

const supplier = {
  id: 42,
  name: "测试供应商",
  brand: "eblan",
  factory_code: "00102",
}
const ledger: CounterpartyLedgerResponse = {
  name: supplier.name,
  counterparty_type: "supplier",
  date_start: "2025-01-01",
  date_end: "2026-08-31",
  beginning_balance: "100",
  increase_total: "109.25",
  decrease_total: "20",
  ending_balance: "189.25",
  items: [
    {
      id: 1,
      row_number: 1,
      date: "2026-01-01",
      document_number: "001",
      document_type: "进货单",
      summary: "小额进货",
      handler: null,
      warehouse: null,
      increase_amount: "9.25",
      decrease_amount: "",
      balance: "109.25",
    },
    {
      id: 2,
      row_number: 2,
      date: "2026-01-02",
      document_number: "002",
      document_type: "进货单",
      summary: "大额进货",
      handler: null,
      warehouse: null,
      increase_amount: "100",
      decrease_amount: "",
      balance: "209.25",
    },
  ],
}
function remember(key: string, value: unknown) {
  window.sessionStorage.setItem(
    `hede:session-query:v1:1:${key}`,
    JSON.stringify(value)
  )
}
function fixture(detail = false) {
  return (
    <SessionQueryProvider userId={1}>
      <PageTabs />
      {detail ? <SupplierLedgerPage id={42} /> : <SuppliersPage />}
    </SessionQueryProvider>
  )
}
beforeEach(() => {
  clearStockModuleQueries()
  vi.clearAllMocks()
  auth.hasPermission.mockReturnValue(true)
  navigation.pathname = "/suppliers"
  api.listSuppliers.mockResolvedValue({
    items: [supplier],
    total: 1,
    page: 1,
    page_size: 30,
  })
  api.listSupplierBrands.mockResolvedValue({ items: [] })
  api.getSupplier.mockResolvedValue({ item: supplier })
  api.getPinnedPageTabs.mockResolvedValue({ pinned_paths: [] })
  api.listCounterpartyLedger.mockImplementation(async (params) => ({
    ...ledger,
    items:
      params.sortBy === "increase_amount" && params.sortDirection === "desc"
        ? [...ledger.items].reverse()
        : ledger.items,
  }))
  api.downloadCounterpartyLedger.mockResolvedValue({ filename: "ledger.xlsx" })
  api.downloadGeneralCustomerLedger.mockResolvedValue({
    filename: "customer.xlsx",
  })
})
afterEach(() => vi.useRealTimers())

test("opens a full-page tab with submitted outer dates and retains its query when switching pages", async () => {
  remember("suppliers:dateStart", "2025-01-01")
  remember("suppliers:dateEnd", "2026-08-31")
  remember("suppliers:dateStartInput", "2025-02-01")
  const user = userEvent.setup()
  const view = render(fixture())
  await user.click(await screen.findByText(supplier.name))
  expect(navigation.push).toHaveBeenCalledWith("/suppliers/42/ledger", {
    scroll: false,
  })
  navigation.pathname = "/suppliers/42/ledger"
  view.rerender(fixture(true))
  await screen.findByRole("heading", { name: "应付款-明细账本" })
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  expect(
    screen.getByRole("link", { name: "测试供应商 · 应付款" })
  ).toHaveAttribute("aria-current", "page")
  expect(screen.getByLabelText("起始日期")).toHaveValue("2025-01-01")
  expect(screen.getByLabelText("截止日期")).toHaveValue("2026-08-31")
  await waitFor(() =>
    expect(api.listCounterpartyLedger).toHaveBeenLastCalledWith(
      expect.objectContaining({
        dateStart: "2025-01-01",
        dateEnd: "2026-08-31",
      }),
      expect.any(AbortSignal)
    )
  )
  await user.click(screen.getByRole("button", { name: "按增加金额排序" }))
  await waitFor(() =>
    expect(
      screen.getByRole("columnheader", { name: /增加金额/ })
    ).toHaveAttribute("aria-sort", "descending")
  )
  await waitFor(() =>
    expect(screen.getAllByRole("row")[1]).toHaveTextContent("大额进货")
  )
  expect(screen.getAllByRole("row")[1]).toHaveTextContent("209.25")
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  expect(api.downloadCounterpartyLedger).toHaveBeenCalledWith(
    "supplier",
    expect.objectContaining({
      name: supplier.name,
      dateStart: "2025-01-01",
      dateEnd: "2026-08-31",
      sortBy: "increase_amount",
      sortDirection: "desc",
    }),
    expect.any(AbortSignal)
  )
  await user.click(screen.getByRole("button", { name: "返回供应商管理" }))
  expect(navigation.push).toHaveBeenLastCalledWith("/suppliers", {
    scroll: false,
  })
  const ledgerCalls = api.listCounterpartyLedger.mock.calls.length
  const supplierCalls = api.getSupplier.mock.calls.length
  navigation.pathname = "/suppliers"
  view.rerender(fixture())
  expect(screen.getByLabelText("起始日期")).toHaveValue("2025-02-01")
  navigation.pathname = "/suppliers/42/ledger"
  view.rerender(fixture(true))
  await screen.findByRole("heading", { name: "应付款-明细账本" })
  expect(screen.getByLabelText("起始日期")).toHaveValue("2025-01-01")
  expect(
    screen.getByRole("columnheader", { name: /增加金额/ })
  ).toHaveAttribute("aria-sort", "descending")
  expect(screen.getByText("大额进货")).toBeInTheDocument()
  expect(api.listCounterpartyLedger).toHaveBeenCalledTimes(ledgerCalls)
  expect(api.getSupplier).toHaveBeenCalledTimes(supplierCalls)

  navigation.pathname = "/suppliers"
  view.rerender(fixture())
  publishBusinessDataChange(["inventory"])
  navigation.pathname = "/suppliers/42/ledger"
  view.rerender(fixture(true))
  await waitFor(() => expect(api.listCounterpartyLedger).toHaveBeenCalledTimes(ledgerCalls + 1))
  expect(api.getSupplier).toHaveBeenCalledTimes(supplierCalls)
})

test.each([
  ["", "", "2026-11-01", "2026-11-19"],
  ["2025-01-01", "", "2025-01-01", ""],
  ["", "2026-08-31", "", "2026-08-31"],
])(
  "uses current month only when the outer range is empty (%s / %s)",
  async (start, end, expectedStart, expectedEnd) => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date(2026, 10, 19, 12))
    remember("suppliers:dateStart", start)
    remember("suppliers:dateEnd", end)
    const view = render(fixture())
    fireEvent.click(await screen.findByText(supplier.name))
    navigation.pathname = "/suppliers/42/ledger"
    view.rerender(fixture(true))
    await waitFor(() =>
      expect(api.listCounterpartyLedger).toHaveBeenCalledWith(
        expect.objectContaining({
          dateStart: expectedStart,
          dateEnd: expectedEnd,
        }),
        expect.any(AbortSignal)
      )
    )
  }
)

test("draft dates do not query or change the export range until submitted; repeated query refreshes", async () => {
  const user = userEvent.setup()
  render(fixture(true))
  await screen.findByText("小额进货")
  const calls = api.listCounterpartyLedger.mock.calls.length
  await user.click(screen.getByRole("button", { name: "设定测试区间" }))
  expect(screen.getByLabelText("起始日期")).toHaveValue("2025-01-01")
  expect(screen.getByLabelText("截止日期")).toHaveValue("2026-08-31")
  expect(api.listCounterpartyLedger).toHaveBeenCalledTimes(calls)
  await user.click(screen.getByRole("button", { name: "导出 Excel" }))
  expect(api.downloadCounterpartyLedger.mock.calls[0][1].dateStart).not.toBe(
    "2025-01-01"
  )
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() =>
    expect(api.listCounterpartyLedger).toHaveBeenLastCalledWith(
      expect.objectContaining({
        dateStart: "2025-01-01",
        dateEnd: "2026-08-31",
      }),
      expect.any(AbortSignal)
    )
  )
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(api.listCounterpartyLedger).toHaveBeenCalledTimes(calls + 2)
  fireEvent.change(screen.getByLabelText("起始日期"), {
    target: { value: "2027-01-01" },
  })
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(screen.getByRole("alert")).toHaveTextContent(
    "起始日期不能晚于截止日期"
  )
  expect(api.listCounterpartyLedger).toHaveBeenCalledTimes(calls + 2)
})

test("ignores a superseded ledger response and reports failures without a false empty result", async () => {
  let resolveOld!: (value: CounterpartyLedgerResponse) => void
  api.listCounterpartyLedger.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveOld = resolve
    })
  )
  const user = userEvent.setup()
  render(fixture(true))
  await waitFor(() =>
    expect(api.listCounterpartyLedger).toHaveBeenCalledTimes(1)
  )
  await user.click(screen.getByRole("button", { name: "按增加金额排序" }))
  await screen.findByText("大额进货")
  await act(async () => resolveOld({ ...ledger, items: [] }))
  expect(screen.getByText("大额进货")).toBeInTheDocument()
  expect(api.listCounterpartyLedger.mock.calls[0][1].aborted).toBe(true)
  api.listCounterpartyLedger.mockRejectedValueOnce(new Error("账本读取失败"))
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("账本读取失败")
  expect(screen.queryByText("该时间范围内暂无单据")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "导出 Excel" })).toBeDisabled()
})

test("view-only users cannot export supplier ledgers", async () => {
  auth.hasPermission.mockImplementation(
    (permission) => permission === "inventory.view"
  )
  render(fixture(true))
  await screen.findByText("小额进货")
  expect(
    screen.queryByRole("button", { name: "导出 Excel" })
  ).not.toBeInTheDocument()
})

test("closing ledger tabs preserves other suppliers and returns to the supplier list", async () => {
  remember("workspace:manual-tabs", [
    "/suppliers",
    "/suppliers/42/ledger",
    "/suppliers/43/ledger",
  ])
  remember("workspace:supplier-ledger-tabs:v1", [
    { id: 42, name: supplier.name, query: defaultLedgerQuery() },
    { id: 43, name: "另一供应商", query: defaultLedgerQuery() },
  ])
  navigation.pathname = "/suppliers/42/ledger"
  const user = userEvent.setup()
  render(fixture(true))
  await screen.findByText("小额进货")
  await user.click(
    screen.getByRole("button", { name: "关闭另一供应商 · 应付款" })
  )
  expect(navigation.push).not.toHaveBeenCalled()
  expect(
    screen.getByRole("link", { name: "测试供应商 · 应付款" })
  ).toBeInTheDocument()
  await user.click(
    screen.getByRole("button", { name: "关闭测试供应商 · 应付款" })
  )
  expect(navigation.push).toHaveBeenLastCalledWith("/suppliers", {
    scroll: false,
  })
  expect(
    JSON.parse(
      window.sessionStorage.getItem(
        "hede:session-query:v1:1:workspace:supplier-ledger-tabs:v1"
      )!
    )
  ).toEqual([])
})

test("the customer ledger dialog keeps its existing export entry and finance restriction", async () => {
  const user = userEvent.setup()
  render(
    <CounterpartyLedgerDialog
      open
      counterpartyType="customer"
      name="测试客户"
      onOpenChange={vi.fn()}
    />
  )
  const dialog = screen.getByRole("dialog")
  await within(dialog).findByText("小额进货")
  await user.click(within(dialog).getByRole("button", { name: "导出 Excel" }))
  expect(api.downloadGeneralCustomerLedger).toHaveBeenCalledWith(
    expect.objectContaining({ name: "测试客户" }),
    expect.any(AbortSignal)
  )
})
