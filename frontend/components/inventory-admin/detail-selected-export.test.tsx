import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

const mocks = vi.hoisted(() => ({ list: vi.fn(), download: vi.fn() }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listPurchaseInboundDetails: mocks.list, listPurchaseOrderDetails: mocks.list, listSalesDetails: mocks.list,
  downloadSelectedDetailExport: mocks.download,
  getSalesDetailOptions: async () => ({ brands: [], customers: [], warehouses: [] }),
  getPurchaseOrderDetailOptions: async () => ({ brands: [], suppliers: [], warehouses: [] }),
  listSuppliers: async () => ({ items: [] }), listWarehouses: async () => ({ items: [] }),
  listInventoryBrands: async () => ({ items: [] }), listInventoryDetailCandidates: async () => ({ items: [] }),
}))

function response(page = 1, barcode = false) {
  const totals = { purchase_quantity: "6", purchase_amount: "12", sales_quantity: "6", sales_amount: "12", retail_amount: "" }
  return {
    total: 51, page, page_size: 50, totals: { ...totals, all: totals, current_page: totals },
    items: (page === 1 ? [11, 12] : [21]).map((id, index) => ({
      detail_id: barcode ? 11 : id, document_id: 1, row_number: (page - 1) * 50 + index + 1,
      row_key: barcode ? `11:0:${id === 21 ? "36" : "35"}` : undefined,
      product_code: barcode ? "SKU-11" : `SKU-${id}`, product_name: "测试鞋", color_name: "黑",
      document_number: "PO-1", document_type: "进货订单", date: "2026-11-10", ...totals,
      unit_name: "测试供应商", unit_code: "001", warehouse_name: "测试仓", unit_price: "2", size_quantities: { "35": 6 },
      ...(barcode ? { size_name: id === 21 ? "36" : "35", barcode: `001${id}`, size_barcode: id === 21 ? "036" : "035" } : {}),
    })),
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  window.sessionStorage.clear()
  mocks.list.mockImplementation(async params => response(params.page, params.display_mode === "barcode"))
  mocks.download.mockResolvedValue({ filename: "明细.xlsx", size: 10 })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const ready = () => waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())

test.each(["orders", "inbound", "sales"] as const)("%s exports exactly the cross-page selection and retains it across sorting and page-size changes", async mode => {
  const user = userEvent.setup()
  render(<PurchaseInboundDetailPage mode={mode} />)
  await ready()
  expect(screen.getByRole("button", { name: "导出所选" })).toBeDisabled()
  await user.click(screen.getByRole("checkbox", { name: "全选本页明细" }))
  expect(screen.getByText("已选 2 条")).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "选择明细 PO-1 SKU-12" }))
  expect(screen.getByRole("checkbox", { name: "全选本页明细" })).toBePartiallyChecked()
  await user.click(screen.getByLabelText("Go to next page"))
  await ready()
  await user.click(screen.getByRole("checkbox", { name: "选择明细 PO-1 SKU-21" }))
  expect(screen.getByText("已选 2 条")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "日期升序，点击切换为降序" }))
  await ready()
  expect(screen.getByRole("checkbox", { name: "选择明细 PO-1 SKU-11" })).toBeChecked()
  expect(screen.getByRole("checkbox", { name: "选择明细 PO-1 SKU-12" })).not.toBeChecked()
  await user.selectOptions(screen.getByRole("combobox", { name: "每页条数" }), "100")
  await ready()
  await user.type(screen.getByRole("textbox", { name: "商品名称" }), "未提交草稿")
  await user.click(screen.getByRole("button", { name: "导出所选" }))
  await waitFor(() => expect(mocks.download).toHaveBeenCalledWith(mode, { sort_direction: "desc" }, ["11", "21"], expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "查询" }))
  await ready()
  expect(screen.getByText("已选 0 条")).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "全选本页明细" }))
  await user.click(screen.getByRole("button", { name: "清空选择" }))
  expect(screen.getByRole("button", { name: "导出所选" })).toBeDisabled()
})

test.each(["inbound", "sales"] as const)("%s selects exact size rows across pages and clears them on display-mode changes", async mode => {
  const user = userEvent.setup()
  // One size on each page of the same source detail.
  mocks.list.mockImplementation(async params => ({ ...response(params.page, params.display_mode === "barcode"), items: response(params.page, params.display_mode === "barcode").items.slice(0, 1) }))
  render(<PurchaseInboundDetailPage mode={mode} />)
  await ready()
  await user.click(screen.getByRole("checkbox", { name: "全选本页明细" }))
  await user.click(screen.getByRole("button", { name: "按编码" }))
  await ready()
  expect(screen.getByText("已选 0 条")).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "选择明细 PO-1 SKU-11 35" }))
  await user.click(screen.getByLabelText("Go to next page"))
  await ready()
  expect(screen.getByRole("checkbox", { name: "选择明细 PO-1 SKU-11 36" })).not.toBeChecked()
  await user.click(screen.getByRole("checkbox", { name: "全选本页明细" }))
  await user.click(screen.getByRole("button", { name: "导出所选" }))
  await waitFor(() => expect(mocks.download).toHaveBeenCalledWith(mode, { sort_direction: "asc", display_mode: "barcode" }, ["11:0:35", "11:0:36"], expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "按货号" }))
  await ready()
  expect(screen.getByText("已选 0 条")).toBeInTheDocument()
})

test.each(["inbound", "sales"] as const)("%s replaces incompatible rows with a loading state when switching to barcode columns", async mode => {
  const user = userEvent.setup()
  render(<PurchaseInboundDetailPage mode={mode} />)
  await ready()
  expect(screen.getByText("SKU-11")).toBeInTheDocument()
  let resolveNext!: (value: ReturnType<typeof response>) => void
  mocks.list.mockReturnValueOnce(new Promise(resolve => { resolveNext = resolve }))
  await user.click(screen.getByRole("button", { name: "按编码" }))
  expect(screen.getByRole("status")).toHaveTextContent("正在加载明细…")
  expect(screen.queryByText("SKU-11")).not.toBeInTheDocument()
  expect(screen.getByRole("columnheader", { name: "商品编码" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "按货号" })).toBeDisabled()
  await act(async () => {
    const next = response(1, true)
    resolveNext({ ...next, items: next.items.slice(0, 1) })
  })
  expect(screen.queryByRole("status")).not.toBeInTheDocument()
  expect(screen.getByText("00111")).toBeInTheDocument()
})

test("selection is isolated by page mode and restored after returning", async () => {
  const user = userEvent.setup()
  const first = render(<PurchaseInboundDetailPage mode="orders" />)
  await ready()
  await user.click(screen.getByRole("checkbox", { name: "全选本页明细" }))
  first.unmount()
  const second = render(<PurchaseInboundDetailPage mode="inbound" />)
  await ready()
  expect(screen.getByText("已选 0 条")).toBeInTheDocument()
  second.unmount()
  render(<PurchaseInboundDetailPage mode="orders" />)
  await ready()
  expect(screen.getByText("已选 2 条")).toBeInTheDocument()
})

test("shows export failures, keeps the selection for retry, blocks duplicate downloads and aborts on unmount", async () => {
  const user = userEvent.setup()
  const view = render(<PurchaseInboundDetailPage mode="orders" />)
  await ready()
  await user.click(screen.getByRole("checkbox", { name: "全选本页明细" }))
  mocks.download.mockRejectedValueOnce(new Error("明细已变更，请重新选择"))
  await user.click(screen.getByRole("button", { name: "导出所选" }))
  expect(await screen.findByText("明细已变更，请重新选择")).toBeInTheDocument()
  expect(screen.getByText("已选 2 条")).toBeInTheDocument()
  let resolve!: () => void
  mocks.download.mockImplementationOnce(() => new Promise<void>(done => { resolve = done }))
  await user.click(screen.getByRole("button", { name: "导出所选" }))
  expect(screen.getByRole("button", { name: "导出所选" })).toBeDisabled()
  await user.click(screen.getByRole("button", { name: "导出所选" }))
  expect(mocks.download).toHaveBeenCalledTimes(2)
  const signal = mocks.download.mock.calls[1][3] as AbortSignal
  view.unmount()
  expect(signal.aborted).toBe(true)
  await act(async () => { resolve() })
})

test("no export permission disables selecting and selected export", async () => {
  render(<PurchaseInboundDetailPage mode="orders" canExport={false} />)
  await ready()
  for (const checkbox of screen.getAllByRole("checkbox")) expect(checkbox).toBeDisabled()
  expect(screen.getByRole("button", { name: "导出所选" })).toBeDisabled()
})
