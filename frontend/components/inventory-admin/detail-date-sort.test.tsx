import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

const mocks = vi.hoisted(() => ({ inbound: vi.fn(), orders: vi.fn(), sales: vi.fn() }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listPurchaseInboundDetails: mocks.inbound,
  listPurchaseOrderDetails: mocks.orders,
  listSalesDetails: mocks.sales,
  getPurchaseOrderDetailOptions: async () => ({ brands: [], suppliers: [], warehouses: [] }),
  getSalesDetailOptions: async () => ({ brands: [], customers: [], warehouses: [] }),
  listSuppliers: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listInventoryBrands: async () => ({ items: [] }),
  listInventoryDetailCandidates: async () => ({ items: [] }),
}))

const amounts = { purchase_quantity: "1", purchase_amount: "10", sales_quantity: "1", sales_amount: "10", retail_amount: "" }
const response = { items: [], total: 101, totals: { ...amounts, all: amounts, current_page: amounts } }
let downloads: string[]

beforeEach(() => {
  vi.resetAllMocks()
  window.sessionStorage.clear()
  for (const mock of Object.values(mocks)) mock.mockResolvedValue(response)
  downloads = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.href) })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test.each(["orders", "inbound", "sales"] as const)("%s sorts all results, resets the page and preserves applied filters, export order and session state", async mode => {
  const user = userEvent.setup()
  const list = mocks[mode]
  let view = render(<PurchaseInboundDetailPage mode={mode} />)
  const ready = () => waitFor(() => expect(screen.getByRole("button", { name: /日期.*点击切换/ })).toBeEnabled())
  const params = () => list.mock.calls.at(-1)![0]
  const header = () => screen.getByRole("button", { name: /日期.*点击切换/ }).closest("th")
  await ready()
  expect(header()).toHaveAttribute("aria-sort", "ascending")
  expect(params()).toMatchObject({ sort_direction: "asc", page: 1 })
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "休闲")
  await user.click(screen.getByRole("button", { name: "查询" }))
  await ready()
  await user.click(screen.getByLabelText("Go to next page"))
  await ready()
  expect(params()).toMatchObject({ product_name: "休闲", page: 2 })
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "草稿")

  let resolve!: (value: typeof response) => void
  list.mockReturnValueOnce(new Promise(done => { resolve = done }))
  await user.click(screen.getByRole("button", { name: "日期升序，点击切换为降序" }))
  expect(params()).toMatchObject({ product_name: "休闲", sort_direction: "desc", page: 1 })
  expect(header()).toHaveAttribute("aria-sort", "descending")
  const sorter = screen.getByRole("button", { name: "日期降序，点击切换为升序" })
  expect(sorter).toBeDisabled()
  const calls = list.mock.calls.length
  fireEvent.click(sorter)
  expect(list).toHaveBeenCalledTimes(calls)
  await act(async () => { resolve(response) })
  await ready()
  await user.click(screen.getByLabelText("Go to next page"))
  await ready()
  expect(params()).toMatchObject({ product_name: "休闲", sort_direction: "desc", page: 2 })
  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  const url = new URL(downloads[0])
  expect(url.searchParams.get("sort_direction")).toBe("desc")
  expect(url.searchParams.get("product_name")).toBe("休闲")
  expect(url.searchParams.has("page")).toBe(false)

  view.unmount()
  const otherMode = mode === "inbound" ? "sales" : "inbound"
  view = render(<PurchaseInboundDetailPage mode={otherMode} />)
  await ready()
  expect(header()).toHaveAttribute("aria-sort", "ascending")
  view.unmount()
  render(<PurchaseInboundDetailPage mode={mode} />)
  await ready()
  expect(params()).toMatchObject({ product_name: "休闲", sort_direction: "desc", page: 2 })
  // Native buttons support keyboard sorting and keep the submitted scope.
  screen.getByRole("button", { name: "日期降序，点击切换为升序" }).focus()
  await user.keyboard("{Enter}")
  await ready()
  expect(header()).toHaveAttribute("aria-sort", "ascending")
  expect(params()).toMatchObject({ product_name: "休闲", sort_direction: "asc", page: 1 })
})

test.each(["inbound", "sales"] as const)("%s switches between goods and actual barcode rows with scoped paging, sorting and export", async mode => {
  const user = userEvent.setup()
  const list = mocks[mode]
  const row = { row_number: 1, row_key: "101:0:35", detail_id: 101, document_id: 11,
    product_code: "001SHOE", product_name: "测试鞋", document_type: mode === "sales" ? "批发销售退货单" : "进货单",
    document_number: "TEST-11", date: "2026-11-10", ...amounts, barcode: "001SHOE010225",
    color_name: "黑", color_barcode: "01", size_name: "35", size_barcode: "0225", barcode_issue: "" }
  const result = { ...response, items: [row, { ...row, row_number: 2, row_key: "102:1:", detail_id: 102,
    barcode: "", size_name: "", size_barcode: "", barcode_issue: "请联系商品部维护尺码组及尺码条码" }] }
  list.mockResolvedValue(result)
  const view = render(<PurchaseInboundDetailPage mode={mode} />)
  const ready = () => waitFor(() => expect(screen.getByRole("button", { name: "按编码" })).toBeEnabled())
  const params = () => list.mock.calls.at(-1)![0]
  await ready()
  expect(screen.getByRole("button", { name: "按货号" })).toHaveAttribute("aria-pressed", "true")
  expect(screen.queryByRole("columnheader", { name: "商品编码" })).not.toBeInTheDocument()
  expect(params().display_mode).toBeUndefined()
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "休闲")
  await user.click(screen.getByRole("button", { name: "查询" }))
  await ready()
  await user.click(screen.getByLabelText("Go to next page"))
  await ready()
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "草稿")
  let resolve!: (value: typeof result) => void
  list.mockReturnValueOnce(new Promise(done => { resolve = done }))
  await user.click(screen.getByRole("button", { name: "按编码" }))
  expect(params()).toMatchObject({ display_mode: "barcode", page: 1, product_name: "休闲", sort_direction: "asc" })
  expect(screen.getByRole("button", { name: "按编码" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "按货号" })).toBeDisabled()
  await act(async () => { resolve(result) })
  await ready()
  for (const name of ["商品编码", "颜色条码", "尺码名称", "尺码条码"]) expect(screen.getByRole("columnheader", { name })).toBeInTheDocument()
  expect(screen.getByText("001SHOE010225")).toBeInTheDocument()
  expect(screen.getByText("0225")).toBeInTheDocument()
  expect(screen.getByText("请联系商品部维护尺码组及尺码条码")).toBeInTheDocument()
  expect(screen.getByRole("row", { name: /全部合计/ }).querySelector("td")).toHaveAttribute("colspan", "12")
  await user.click(screen.getByRole("button", { name: "日期升序，点击切换为降序" }))
  await ready()
  await user.click(screen.getByLabelText("Go to next page"))
  await ready()
  expect(params()).toMatchObject({ display_mode: "barcode", page: 2, product_name: "休闲", sort_direction: "desc" })
  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  const url = new URL(downloads[0])
  expect(url.searchParams.get("display_mode")).toBe("barcode")
  expect(url.searchParams.get("sort_direction")).toBe("desc")
  expect(url.searchParams.get("product_name")).toBe("休闲")
  view.unmount()
  const other = render(<PurchaseInboundDetailPage mode={mode === "inbound" ? "sales" : "inbound"} />)
  await ready()
  expect(screen.getByRole("button", { name: "按货号" })).toHaveAttribute("aria-pressed", "true")
  other.unmount()
  render(<PurchaseInboundDetailPage mode={mode} />)
  await ready()
  expect(screen.getByRole("button", { name: "按编码" })).toHaveAttribute("aria-pressed", "true")
  expect(params()).toMatchObject({ display_mode: "barcode", page: 2 })
  screen.getByRole("button", { name: "按货号" }).focus()
  await user.keyboard("{Enter}")
  await ready()
  expect(screen.queryByRole("columnheader", { name: "商品编码" })).not.toBeInTheDocument()
  expect(params()).toMatchObject({ page: 1, product_name: "休闲", sort_direction: "desc" })
  expect(params().display_mode).toBeUndefined()
})

test("purchase order details do not offer the inbound and sales barcode mode", async () => {
  render(<PurchaseInboundDetailPage mode="orders" />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  expect(screen.queryByRole("group", { name: "明细展示方式" })).not.toBeInTheDocument()
  expect(mocks.orders.mock.calls.at(-1)![0].display_mode).toBeUndefined()
})
