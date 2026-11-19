import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { GeneralCustomerShopsTab } from "@/components/inventory-admin/general-customer-shops-tab"
import type { GeneralCustomerShopItem } from "@/lib/types"

const { api } = vi.hoisted(() => ({
  api: {
    listGeneralCustomerBrands: vi.fn(),
    listGeneralCustomerShops: vi.fn(),
    listGeneralCustomerUnits: vi.fn(),
    getGeneralCustomerBalances: vi.fn(),
    deleteGeneralCustomerShop: vi.fn(),
    setGeneralCustomerShopStatus: vi.fn(),
  },
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  ...api,
}))

vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/inventory-admin/counterparty-ledger-dialog", () => ({
  CounterpartyLedgerDialog: ({ open, name, queryState }: { open: boolean; name: string; queryState?: { dateStart: string; dateEnd: string } }) => open ? <div><p>查账：{name}</p><p>账本区间：{queryState?.dateStart} 至 {queryState?.dateEnd}</p></div> : null,
}))

let shop: GeneralCustomerShopItem

beforeEach(() => {
  vi.clearAllMocks()
  shop = {
    id: 1, customer_name: "测试品牌", shop_name: "测试店铺",
    sort_order: 1, unit_count: 1, is_active: true, has_history: true,
    created_at: null, updated_at: null,
  }
  api.listGeneralCustomerBrands.mockResolvedValue({ items: [{ id: 1, name: "测试品牌", shop_count: 1 }] })
  api.listGeneralCustomerShops.mockImplementation(async () => ({ items: [{ ...shop }] }))
  api.listGeneralCustomerUnits.mockResolvedValue({ items: [{ id: 1, shop_id: 1, unit_name: "测试单位" }] })
  api.getGeneralCustomerBalances.mockResolvedValue({ items: [
    { name: "测试店铺", ending_balance: "0" },
    { name: "测试单位", ending_balance: "-1234.50" },
  ] })
  api.deleteGeneralCustomerShop.mockImplementation(async () => {
    shop = { ...shop, is_active: false }
    return { item: shop, message: "已停用" }
  })
  api.setGeneralCustomerShopStatus.mockImplementation(async (_id: number, is_active: boolean) => {
    shop = { ...shop, is_active }
    return { item: shop, message: "已启用" }
  })
})

afterEach(() => { cleanup(); vi.useRealTimers() })

test("disables a shop with history and preserves shop and unit ledger links", async () => {
  const user = userEvent.setup()
  render(<GeneralCustomerShopsTab standalone />)
  await user.click(await screen.findByRole("button", { name: "停用店铺 测试店铺" }))
  const confirmation = screen.getByRole("alertdialog")
  expect(confirmation).toHaveTextContent("保留店铺、下属单位、历史单据和查账入口")
  await user.click(within(confirmation).getByRole("button", { name: "停用" }))
  await screen.findByText("操作成功")
  await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "确定" }))
  expect(screen.getByText("已停用")).toBeInTheDocument()
  expect(api.deleteGeneralCustomerShop).toHaveBeenCalledWith(1)
  expect(screen.getByRole("button", { name: "新增单位" })).toBeDisabled()
  expect(screen.queryByRole("button", { name: "删除店铺 测试店铺" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: /测试店铺.*1 个单位/ }))
  expect(screen.getByText("查账：测试店铺")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "测试单位" }))
  expect(screen.getByText("查账：测试单位")).toBeInTheDocument()
})

test("allows a disabled shop to be enabled again", async () => {
  shop.is_active = false
  const user = userEvent.setup()
  render(<GeneralCustomerShopsTab />)
  await user.click(await screen.findByRole("button", { name: "启用店铺 测试店铺" }))
  await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "启用" }))
  await waitFor(() => expect(screen.queryByText("已停用")).not.toBeInTheDocument())
  expect(api.setGeneralCustomerShopStatus).toHaveBeenCalledWith(1, true)
  expect(screen.getByRole("button", { name: "新增单位" })).toBeEnabled()
})

test("keeps deletion available only for shops without historical business", async () => {
  shop.has_history = false
  const user = userEvent.setup()
  render(<GeneralCustomerShopsTab />)
  await user.click(await screen.findByRole("button", { name: "删除店铺 测试店铺" }))
  const confirmation = screen.getByRole("alertdialog")
  expect(confirmation).toHaveTextContent("如果已有历史业务，系统会改为停用")
  expect(within(confirmation).getByRole("button", { name: "删除" })).toBeInTheDocument()
})

test("rolls up unit balances into the shop without opening ledgers", async () => {
  render(<GeneralCustomerShopsTab standalone />)
  await waitFor(() => expect(screen.getByLabelText("店铺 测试店铺期末余额")).toHaveTextContent("-1,234.50"))
  expect(screen.getByLabelText("单位 测试单位期末余额")).toHaveTextContent("-1,234.50")
  expect(screen.queryByText(/查账：/)).not.toBeInTheDocument()
  expect(api.getGeneralCustomerBalances).toHaveBeenCalledTimes(1)
})

test("includes own and child balances exactly once, isolates shops and keeps the total when collapsed", async () => {
  const user = userEvent.setup()
  api.listGeneralCustomerShops.mockResolvedValue({ items: [shop, { ...shop, id: 2, shop_name: "其他店铺" }] })
  api.listGeneralCustomerUnits.mockResolvedValue({ items: [
    { id: 1, shop_id: 1, unit_name: "测试单位" },
    { id: 2, shop_id: 1, unit_name: "测试店铺" },
    { id: 3, shop_id: 1, unit_name: "其他单位" },
    { id: 4, shop_id: 2, unit_name: "另一店单位" },
  ] })
  api.getGeneralCustomerBalances.mockResolvedValue({ items: [
    { name: "测试店铺", ending_balance: "10.005" },
    { name: "测试单位", ending_balance: "-1.0049" },
    { name: "其他单位", ending_balance: "0.0049" },
    { name: "其他店铺", ending_balance: "0" },
    { name: "另一店单位", ending_balance: "100" },
  ] })
  render(<GeneralCustomerShopsTab />)
  await waitFor(() => expect(screen.getByLabelText("店铺 测试店铺期末余额")).toHaveTextContent("9.01"))
  expect(screen.getByLabelText("店铺 其他店铺期末余额")).toHaveTextContent("100.00")
  await user.click(screen.getByRole("button", { name: "收起单位 测试店铺" }))
  expect(screen.queryByRole("button", { name: "测试单位" })).not.toBeInTheDocument()
  expect(screen.getByLabelText("店铺 测试店铺期末余额")).toHaveTextContent("9.01")
  api.getGeneralCustomerBalances.mockResolvedValue({ items: [
    { name: "测试店铺", ending_balance: "0" },
    { name: "测试单位", ending_balance: "0" },
    { name: "其他单位", ending_balance: "0" },
    { name: "其他店铺", ending_balance: "0" },
    { name: "另一店单位", ending_balance: "0" },
  ] })
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(screen.getByLabelText("店铺 测试店铺期末余额")).toHaveTextContent("0.00"))
})

test("shows unknown totals when any unit balance is missing and zero for shops without transactions", async () => {
  api.getGeneralCustomerBalances.mockResolvedValue({ items: [{ name: "测试店铺", ending_balance: "0" }] })
  const first = render(<GeneralCustomerShopsTab />)
  await waitFor(() => expect(screen.getByLabelText("店铺 测试店铺期末余额")).toHaveTextContent("—"))
  expect(screen.getByLabelText("单位 测试单位期末余额")).toHaveTextContent("—")
  first.unmount()
  api.listGeneralCustomerUnits.mockResolvedValue({ items: [] })
  render(<GeneralCustomerShopsTab />)
  await waitFor(() => expect(screen.getByLabelText("店铺 测试店铺期末余额")).toHaveTextContent("0.00"))
})

test("queries selected dates, inherits the submitted range in ledgers and keeps it when returning", async () => {
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date(2026, 10, 19, 12))
  const user = userEvent.setup()
  const view = render(<GeneralCustomerShopsTab standalone />)
  await waitFor(() => expect(api.getGeneralCustomerBalances).toHaveBeenCalledWith({ dateStart: "2026-11-01", dateEnd: "2026-11-19" }, expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: /^日期范围：/ }))
  fireEvent.change(screen.getByLabelText("日期范围开始日期"), { target: { value: "2025-01-01" } })
  fireEvent.change(screen.getByLabelText("日期范围结束日期"), { target: { value: "2026-08-31" } })
  expect(api.getGeneralCustomerBalances).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole("button", { name: "完成" }))
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(api.getGeneralCustomerBalances).toHaveBeenLastCalledWith({ dateStart: "2025-01-01", dateEnd: "2026-08-31" }, expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "测试单位" }))
  expect(screen.getByText("账本区间：2025-01-01 至 2026-08-31")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(api.getGeneralCustomerBalances).toHaveBeenCalledTimes(3))
  view.unmount()
  render(<GeneralCustomerShopsTab standalone />)
  expect(screen.getByRole("button", { name: /^日期范围：2025-01-01至2026-08-31/ })).toBeInTheDocument()
  await waitFor(() => expect(api.getGeneralCustomerBalances).toHaveBeenCalledTimes(4))
})

test("cleared dates query all history and are also cleared in the opened ledger", async () => {
  const user = userEvent.setup()
  render(<GeneralCustomerShopsTab />)
  await screen.findByText("测试单位")
  await user.click(screen.getByRole("button", { name: "清空日期" }))
  await waitFor(() => expect(api.getGeneralCustomerBalances).toHaveBeenLastCalledWith({ dateStart: "", dateEnd: "" }, expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "测试单位" }))
  expect(screen.getByText("账本区间： 至")).toBeInTheDocument()
})

test("balance failures are reported and cannot be mistaken for zero balances", async () => {
  api.getGeneralCustomerBalances.mockRejectedValueOnce(new Error("余额读取失败"))
  render(<GeneralCustomerShopsTab />)
  expect(await screen.findByRole("alert")).toHaveTextContent("余额读取失败")
  expect(screen.queryByLabelText("单位 测试单位期末余额")).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "查询" }))
  expect(await screen.findByText("测试单位")).toBeInTheDocument()
})

test("ignores an old balance response after leaving and reopening the page", async () => {
  let resolveOld!: (value: { items: { name: string; ending_balance: string }[] }) => void
  api.getGeneralCustomerBalances.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
  const first = render(<GeneralCustomerShopsTab />)
  await waitFor(() => expect(api.getGeneralCustomerBalances).toHaveBeenCalledTimes(1))
  first.unmount()
  render(<GeneralCustomerShopsTab />)
  await screen.findByText("测试单位")
  await act(async () => resolveOld({ items: [{ name: "测试单位", ending_balance: "999999" }] }))
  expect(screen.getByLabelText("单位 测试单位期末余额")).toHaveTextContent("-1,234.50")
  expect(api.getGeneralCustomerBalances.mock.calls[0][1].aborted).toBe(true)
})
