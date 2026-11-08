import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { PurchaseOrderDetailPage } from "@/components/inventory-admin/purchase-order-detail-page"
import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

const mocks = vi.hoisted(() => ({
  list: vi.fn(), options: vi.fn(), inbound: vi.fn(), inventoryOptions: vi.fn(), candidates: vi.fn(),
  permissions: new Set<string>(),
}))

vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => ({ hasPermission: (permission: string) => mocks.permissions.has(permission) }) }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listPurchaseOrderDetails: mocks.list,
  getPurchaseOrderDetailOptions: mocks.options,
  listPurchaseInboundDetails: mocks.inbound,
  listSuppliers: mocks.inventoryOptions,
  listWarehouses: mocks.inventoryOptions,
  listInventoryBrands: mocks.inventoryOptions,
  listInventoryDetailCandidates: mocks.candidates,
}))

const totals = { purchase_quantity: "5", purchase_amount: "51.25", retail_amount: "" }
function response(code = "SKU-A") {
  return {
    total: 101, totals: { ...totals, current_page: totals, all: totals },
    items: [{ detail_id: 11, document_id: 1, row_number: 1, product_code: code, product_name: "女休闲鞋",
      document_type: "进货订单", document_number: "PO-1", date: "2026-11-01", color_name: "黑色",
      size_quantities: { "230": "2", "235": "3" }, unit_price: "10.25", ...totals,
      unit_name: "女鞋厂", unit_code: "FACT-1", warehouse_name: "仙岩仓" }],
  }
}
let downloads: string[] = []

beforeEach(() => {
  vi.resetAllMocks()
  window.sessionStorage.clear()
  mocks.permissions.clear()
  mocks.permissions.add("purchase.view")
  mocks.permissions.add("purchase.export")
  mocks.list.mockResolvedValue(response())
  mocks.inbound.mockResolvedValue(response("INBOUND-SKU"))
  mocks.inventoryOptions.mockResolvedValue({ items: [] })
  mocks.options.mockResolvedValue({ brands: [{ value: "cbanner_womens", label: "千百度女鞋" }, { value: "custom", label: "自定义品牌" }],
    suppliers: [{ name: "女鞋厂", factory_code: "FACT-1" }], warehouses: [{ name: "仙岩仓", brand: "千百度女鞋" }, { name: "总仓", brand: "custom" }] })
  downloads = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.href) })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

async function openPage() {
  const user = userEvent.setup()
  const view = render(<PurchaseOrderDetailPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  return { user, ...view }
}

test("shows purchase product rows with sizes and unit prices using purchase-only endpoints", async () => {
  const { user } = await openPage()
  expect(screen.getByRole("heading", { name: "采购明细" })).toBeInTheDocument()
  for (const title of ["采购数量", "采购金额", "采购单价", "尺码及数量", "颜色名称"]) {
    expect(screen.getByRole("columnheader", { name: title })).toBeInTheDocument()
  }
  expect(screen.getByText("230: 2；235: 3")).toBeInTheDocument()
  expect(screen.getByText("10.25")).toBeInTheDocument()
  expect(screen.getByRole("combobox", { name: "单据类型" })).toHaveValue("进货订单")
  expect(screen.getByRole("combobox", { name: "单据类型" })).toBeDisabled()
  expect(mocks.options).toHaveBeenCalledOnce()
  expect(mocks.inbound).not.toHaveBeenCalled()
  expect(mocks.inventoryOptions).not.toHaveBeenCalled()
  await user.type(screen.getByRole("combobox", { name: "货号" }), "SKU")
  expect(mocks.candidates).not.toHaveBeenCalled()
})

test("submits multiple brands and warehouses, then reuses the submitted scope for paging and export", async () => {
  const { user } = await openPage()
  const calls = mocks.list.mock.calls.length
  await user.click(screen.getByRole("combobox", { name: "品牌" }))
  await user.click(await screen.findByRole("button", { name: "千百度女鞋" }))
  await user.click(await screen.findByRole("button", { name: "自定义品牌" }))
  await user.click(screen.getByRole("combobox", { name: "仓库全名" }))
  await user.click(await screen.findByRole("button", { name: "仙岩仓" }))
  await user.click(await screen.findByRole("button", { name: "总仓" }))
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "休闲")
  expect(mocks.list).toHaveBeenCalledTimes(calls)
  await user.click(screen.getByRole("button", { name: "查询" }))
  const scope = { brands: ["cbanner_womens", "custom"], warehouse: ["仙岩仓", "总仓"], product_name: "休闲" }
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ ...scope, page: 1 }), expect.any(AbortSignal)))
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ ...scope, page: 2 }), expect.any(AbortSignal)))
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "草稿")
  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  const url = new URL(downloads[0])
  expect(url.pathname).toBe("/api/purchase-order-details/export")
  expect(url.searchParams.getAll("brands")).toEqual(scope.brands)
  expect(url.searchParams.getAll("warehouse")).toEqual(scope.warehouse)
  expect(url.searchParams.get("product_name")).toBe("休闲")
  await user.click(screen.getByRole("button", { name: "清空" }))
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 1, pageSize: 50 }, expect.any(AbortSignal)))
})

test("purchase filters are isolated from inbound filters and restored after returning", async () => {
  const { user, unmount } = await openPage()
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "采购筛选")
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ product_name: "采购筛选" }), expect.any(AbortSignal)))
  unmount()
  const inbound = render(<PurchaseInboundDetailPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  expect(screen.getByRole("textbox", { name: "商品名称" })).toHaveValue("")
  expect(mocks.inbound).toHaveBeenLastCalledWith({ page: 1, pageSize: 50 })
  inbound.unmount()
  render(<PurchaseOrderDetailPage />)
  expect(screen.getByRole("textbox", { name: "商品名称" })).toHaveValue("采购筛选")
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ product_name: "采购筛选" }), expect.any(AbortSignal)))
})

test("denies the page without purchase.view and disables export without purchase.export", async () => {
  mocks.permissions.clear()
  const denied = render(<PurchaseOrderDetailPage />)
  expect(screen.getByText("无权查看采购明细")).toBeInTheDocument()
  expect(mocks.list).not.toHaveBeenCalled()
  denied.unmount()
  mocks.permissions.add("purchase.view")
  await openPage()
  expect(screen.getByRole("button", { name: "导出Excel" })).toBeDisabled()
})

test("aborts obsolete requests and ignores their late results", async () => {
  let resolveOld!: (value: ReturnType<typeof response>) => void
  mocks.list.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
  const user = userEvent.setup()
  render(<PurchaseOrderDetailPage />)
  await waitFor(() => expect(mocks.list).toHaveBeenCalledOnce())
  const oldSignal = mocks.list.mock.calls[0][1] as AbortSignal
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "新条件{Enter}")
  await waitFor(() => expect(screen.getByText("SKU-A")).toBeInTheDocument())
  expect(oldSignal.aborted).toBe(true)
  await act(async () => { resolveOld(response("STALE-SKU")) })
  expect(screen.queryByText("STALE-SKU")).not.toBeInTheDocument()
  expect(screen.getByText("SKU-A")).toBeInTheDocument()
})
