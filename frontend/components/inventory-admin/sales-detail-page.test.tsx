import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { SalesDetailPage } from "@/components/inventory-admin/sales-detail-page"
import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

const mocks = vi.hoisted(() => ({ list: vi.fn(), options: vi.fn(), log: vi.fn(), canExport: true }))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ hasPermission: (permission: string) => permission !== "inventory.export" || mocks.canExport }),
}))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: (props: unknown) => { mocks.log(props); return null },
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listSalesDetails: mocks.list,
  getSalesDetailOptions: mocks.options,
  listInventoryDetailCandidates: async () => ({ items: [] }),
  listPurchaseInboundDetails: async () => ({ items: [], total: 0, totals: { all: {} } }),
  listSuppliers: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listInventoryBrands: async () => ({ items: [] }),
}))

let downloads: string[] = []
beforeEach(() => {
  vi.resetAllMocks()
  window.localStorage.clear()
  window.sessionStorage.clear()
  mocks.canExport = true
  mocks.options.mockResolvedValue({
    brands: [{ value: "yandou", label: "烟斗" }],
    customers: [{ name: "杭州客户" }, { name: "广州客户" }],
    warehouses: [{ name: "总仓", brand: "烟斗" }],
  })
  const totals = { sales_quantity: "8", sales_amount: "120", retail_amount: "" }
  mocks.list.mockResolvedValue({
    total: 101, page: 1, page_size: 50,
    items: [{
      row_number: 1, detail_id: 111, document_id: 11, product_code: "SKU-A", product_name: "休闲鞋",
      document_type: "批发销售退货单", document_number: "RETURN-1", date: "2026-11-09",
      sales_quantity: "-2", sales_amount: "-30", retail_amount: "", unit_code: "", unit_name: "杭州客户", warehouse_name: "总仓",
    }],
    totals: { ...totals, all: totals, current_page: { sales_quantity: "-2", sales_amount: "-30", retail_amount: "" } },
  })
  downloads = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.href) })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

async function openPage() {
  const user = userEvent.setup()
  const rendered = render(<SalesDetailPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  return { user, ...rendered }
}

test("shows sales columns, return signs, totals and only the two wholesale document filters", async () => {
  await openPage()
  expect(screen.getByRole("heading", { name: "商品销售明细" })).toBeInTheDocument()
  expect(screen.getByRole("columnheader", { name: "销售数量" })).toBeInTheDocument()
  expect(screen.getByRole("columnheader", { name: "销售金额" })).toBeInTheDocument()
  expect(screen.queryByRole("columnheader", { name: "进货金额" })).not.toBeInTheDocument()
  const types = screen.getByRole("combobox", { name: "单据类型" })
  expect(within(types).getAllByRole("option").map((item) => item.textContent)).toEqual(["全部", "批发销售单", "批发销售退货单"])
  const row = screen.getByRole("row", { name: /SKU-A/ })
  expect(within(row).getByText("-2")).toHaveClass("text-destructive")
  expect(within(row).getByText("-30")).toHaveClass("text-destructive")
  const totals = screen.getByRole("row", { name: /全部合计/ })
  expect(within(totals).getByText("8")).toBeInTheDocument()
  expect(within(totals).getByText("120")).toBeInTheDocument()
  expect(mocks.log).toHaveBeenLastCalledWith(expect.objectContaining({ module: "sales_detail", title: "商品销售明细操作日志" }))
})

test("applies customer, type, brand and warehouse filters on search and preserves them in pagination and export", async () => {
  const { user } = await openPage()
  const calls = mocks.list.mock.calls.length
  await user.selectOptions(screen.getByRole("combobox", { name: "单据类型" }), "批发销售退货单")
  await user.type(screen.getByRole("combobox", { name: "单位全名" }), "杭州")
  await user.click(await screen.findByRole("button", { name: "杭州客户" }))
  await user.click(screen.getByRole("combobox", { name: "品牌" }))
  await user.click(await screen.findByRole("button", { name: "烟斗" }))
  await user.click(screen.getByRole("combobox", { name: "仓库全名" }))
  await user.click(await screen.findByRole("button", { name: "总仓" }))
  expect(mocks.list).toHaveBeenCalledTimes(calls)
  await user.click(screen.getByRole("button", { name: "查询" }))
  const filters = { document_type: "批发销售退货单", supplier: "杭州客户", brands: ["yandou"], warehouse: ["总仓"] }
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ ...filters, page: 1 }), expect.any(AbortSignal)))
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ ...filters, page: 2 }), expect.any(AbortSignal)))
  await user.selectOptions(screen.getByRole("combobox", { name: "单据类型" }), "批发销售单")
  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  const url = new URL(downloads[0])
  expect(url.pathname).toBe("/api/inventory-reports/sales-details/export")
  expect(url.searchParams.get("document_type")).toBe("批发销售退货单")
  expect(url.searchParams.get("supplier")).toBe("杭州客户")
  expect(url.searchParams.getAll("brands")).toEqual(["yandou"])
  expect(url.searchParams.getAll("warehouse")).toEqual(["总仓"])
  expect(url.searchParams.has("page")).toBe(false)
  await user.click(screen.getAllByRole("button", { name: "清空" }).find((button) => button.textContent?.includes("清空"))!)
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith({ page: 1, pageSize: 50, sort_direction: "asc" }, expect.any(AbortSignal)))
})

test("keeps sales filters separate from inbound and restores them when returning", async () => {
  const { user, unmount } = await openPage()
  await user.selectOptions(screen.getByRole("combobox", { name: "单据类型" }), "批发销售退货单")
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ document_type: "批发销售退货单" }), expect.any(AbortSignal)))
  unmount()
  const inbound = render(<PurchaseInboundDetailPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  expect(screen.getByRole("combobox", { name: "单据类型" })).toHaveValue("")
  inbound.unmount()
  render(<SalesDetailPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  expect(screen.getByRole("combobox", { name: "单据类型" })).toHaveValue("批发销售退货单")
})

test("disables export without inventory export permission", async () => {
  mocks.canExport = false
  await openPage()
  expect(screen.getByRole("button", { name: "导出Excel" })).toBeDisabled()
})

test("shows a recoverable list error", async () => {
  mocks.list.mockRejectedValueOnce(new Error("查询失败"))
  const { user } = await openPage()
  expect(await screen.findByRole("alert")).toHaveTextContent("查询失败")
  expect(screen.getByText("没有符合条件的销售明细")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(await screen.findByRole("row", { name: /SKU-A/ })).toBeInTheDocument()
})
