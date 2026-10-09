import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { GeneralCustomerShopsTab } from "@/components/inventory-admin/general-customer-shops-tab"
import type { GeneralCustomerShopItem } from "@/lib/types"

const { api } = vi.hoisted(() => ({
  api: {
    listGeneralCustomerBrands: vi.fn(),
    listGeneralCustomerShops: vi.fn(),
    listGeneralCustomerUnits: vi.fn(),
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
  CounterpartyLedgerDialog: ({ open, name }: { open: boolean; name: string }) => open ? <div>查账：{name}</div> : null,
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
  api.deleteGeneralCustomerShop.mockImplementation(async () => {
    shop = { ...shop, is_active: false }
    return { item: shop, message: "已停用" }
  })
  api.setGeneralCustomerShopStatus.mockImplementation(async (_id: number, is_active: boolean) => {
    shop = { ...shop, is_active }
    return { item: shop, message: "已启用" }
  })
})

afterEach(cleanup)

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
