import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import type { ProductListItem } from "@/lib/types"

const { listMock, selectionMock, deleteMock, canManage } = vi.hoisted(() => ({
  listMock: vi.fn(), selectionMock: vi.fn(), deleteMock: vi.fn(), canManage: { value: true },
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, role_code: "super_admin" }, hasPermission: (permission: string) => permission !== "product.manage" || canManage.value }),
}))
vi.mock("@/components/product-admin/product-form-dialog", () => ({ ProductFormDialog: () => null }))
vi.mock("@/components/product-admin/product-detail-dialog", () => ({ ProductDetailDialog: () => null }))
vi.mock("@/components/product-admin/product-copywriting-dialog", () => ({ ProductCopywritingDialog: () => null }))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: listMock,
  listProductSelectionIds: selectionMock,
  batchDeleteProducts: deleteMock,
  listProductArchiveBrands: async () => ({ items: [{ id: 99, code: "new_brand", name: "新增品牌", sort_order: 99 }] }),
  getProductYears: async () => ({ years: ["2025", "2026"] }),
  getProductImageRefreshStatus: async () => ({ in_progress: false }),
}))

function product(page: number, brand = "all") {
  return {
    id: 1,
    brand: brand === "all" ? page === 1 ? "cbanner_mens" : "cbanner_womens" : brand,
    sku: `SKU-${page}`,
    original_sku: `ORIG-${page}`,
    image_path: null, image_url: null, product_name: null, group_name: null, category: null,
    product_level: null, cost: null, factory_sku: null, color: null, season_category: null, year: null,
    upper_material: null, lining_material: null, outsole_material: null, insole_material: null,
    execution_standard: null, heel_height: null, shoe_width: null, shoe_length: null,
    shaft_circumference: null, shaft_height: null, internal_height_increase: null,
    internal_height_note: null, upper_height: null, toe_shape: null, closure_type: null,
    shoe_box_spec: null, shoe_box_type: null, selling_points: null, first_order_time: null,
    size_range: null, product_model: null, supplier_name: null, color_code: null,
    barcode_build_rule: null, launch_date: null,
    source_workbook: "test", source_sheet: "test", source_row_number: "1",
  } satisfies ProductListItem
}

beforeEach(() => {
  vi.resetAllMocks()
  window.sessionStorage.clear()
  clearSessionQueryStates()
  window.history.replaceState({}, "", "/products")
  canManage.value = true
  listMock.mockImplementation(async ({ brand, page }) => ({ items: [product(page, brand)], total: 25, page, page_size: 10 }))
  selectionMock.mockResolvedValue({ items: [
    { brand: "cbanner_mens", id: 1 }, { brand: "cbanner_womens", id: 1 }, { brand: "new_brand", id: 99 },
  ], total: 3 })
  deleteMock.mockResolvedValue({ deleted: 2, message: "已移入回收站 2 条商品" })
})

afterEach(() => cleanup())

async function openPage() {
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  await waitFor(() => expect(screen.getByRole("checkbox", { name: "选择当前页全部商品" })).toBeEnabled())
  return user
}

async function nextPage(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() => expect(screen.getByRole("checkbox", { name: "选择商品 SKU-2" })).toBeEnabled())
}

test("cross-page selection keeps the same numeric ID in different brands and confirms a fixed snapshot", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await nextPage(user)
  expect(screen.getByText("已选 1 个商品")).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-2" }))
  expect(screen.getByText("已选 2 项（跨页保留）")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "批量删除" }))
  const confirmation = within(screen.getByRole("alertdialog", { name: "确认批量删除" }))
  expect(confirmation.getByText(/跨页选中的 2 条商品/)).toHaveTextContent("不仅是当前页")
  expect(deleteMock).not.toHaveBeenCalled()
  await user.click(confirmation.getByRole("button", { name: "移入回收站" }))
  await waitFor(() => expect(deleteMock).toHaveBeenCalledExactlyOnceWith([
    { brand: "cbanner_mens", id: 1 }, { brand: "cbanner_womens", id: 1 },
  ]))
  await waitFor(() => expect(listMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 })))
  expect(await screen.findByRole("alertdialog", { name: "已移入回收站" })).toHaveTextContent("已移入回收站 2 条商品")
})

test("current-page deselection and page-size changes preserve other pages", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择当前页全部商品" }))
  await nextPage(user)
  await user.click(screen.getByRole("checkbox", { name: "选择当前页全部商品" }))
  expect(screen.getByText("已选 2 个商品")).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "选择当前页全部商品" }))
  expect(screen.getByText("已选 1 个商品")).toBeInTheDocument()
  await user.selectOptions(screen.getByRole("combobox", { name: "每页条数" }), "50")
  await waitFor(() => expect(screen.getByRole("checkbox", { name: "选择商品 SKU-1" })).toBeChecked())
  expect(screen.getByText("已选 1 个商品")).toBeInTheDocument()
})

test("select-all uses committed filters, supports exclusions, and does not query again on deletion", async () => {
  selectionMock.mockResolvedValueOnce({ items: [
    { brand: "new_brand", id: 1 }, { brand: "new_brand", id: 2 }, { brand: "new_brand", id: 99 },
  ], total: 3 })
  const user = await openPage()
  await user.click(screen.getByRole("tab", { name: "新增品牌" }))
  await user.type(screen.getByRole("textbox", { name: "包含搜索" }), "AA")
  await user.type(screen.getByRole("textbox", { name: "货号前缀" }), "A")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(screen.getByRole("button", { name: "全选筛选结果" })).toBeEnabled())
  await user.type(screen.getByRole("textbox", { name: "包含搜索" }), "未提交")
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(selectionMock).toHaveBeenCalledExactlyOnceWith({ brand: "new_brand", query: "AA", skuPrefix: "A", year: undefined })
  expect(screen.getByText("已选 3 项（全部筛选结果）")).toBeInTheDocument()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(screen.getByRole("button", { name: "批量删除" }))
  await user.click(within(screen.getByRole("alertdialog", { name: "确认批量删除" })).getByRole("button", { name: "移入回收站" }))
  await waitFor(() => expect(deleteMock).toHaveBeenCalledOnce())
  expect(deleteMock.mock.calls[0][0]).toEqual([
    { brand: "new_brand", id: 2 }, { brand: "new_brand", id: 99 },
  ])
  expect(selectionMock).toHaveBeenCalledOnce()
})

test("repeating the same search clears selection and ignores a late select-all response", async () => {
  let resolve!: (result: { items: Array<{ brand: string; id: number }>; total: number }) => void
  selectionMock.mockReturnValueOnce(new Promise((onResolve) => { resolve = onResolve }))
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(screen.getByRole("button", { name: "正在全选..." })).toBeDisabled()
  expect(screen.getByRole("checkbox", { name: "选择商品 SKU-1" })).toBeDisabled()
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await act(async () => resolve({ items: [{ brand: "cbanner_mens", id: 1 }], total: 1 }))
  expect(screen.queryByRole("button", { name: "批量删除" })).not.toBeInTheDocument()
  expect(screen.getByRole("checkbox", { name: "选择商品 SKU-1" })).not.toBeChecked()
  expect(deleteMock).not.toHaveBeenCalled()
})

test("changing brand or year clears cross-page selection", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(screen.getByRole("tab", { name: "新增品牌" }))
  await waitFor(() => expect(screen.queryByRole("button", { name: "批量删除" })).not.toBeInTheDocument())
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(await screen.findByRole("button", { name: "2025" }))
  expect(screen.queryByRole("button", { name: "批量删除" })).not.toBeInTheDocument()
})

test("canceling deletion does not mutate and keeps selections until explicitly cleared", async () => {
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(screen.getByRole("button", { name: "批量删除" }))
  await user.click(within(screen.getByRole("alertdialog", { name: "确认批量删除" })).getByRole("button", { name: "取消" }))
  expect(deleteMock).not.toHaveBeenCalled()
  expect(screen.getByText("已选 1 个商品")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "清空选择" }))
  expect(screen.queryByRole("button", { name: "批量删除" })).not.toBeInTheDocument()
})

test("selection errors retain explicit choices and deletion errors retain the selection for retry", async () => {
  selectionMock.mockRejectedValueOnce(new Error("查询失败"))
  deleteMock.mockRejectedValueOnce(new Error("删除中断"))
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(screen.getByRole("button", { name: "全选筛选结果" }))
  expect(await screen.findByRole("alertdialog", { name: "全选失败" })).toHaveTextContent("查询失败")
  await user.click(screen.getByRole("button", { name: "确定" }))
  expect(screen.getByRole("checkbox", { name: "选择商品 SKU-1" })).toBeChecked()
  await user.click(screen.getByRole("button", { name: "批量删除" }))
  await user.click(within(screen.getByRole("alertdialog", { name: "确认批量删除" })).getByRole("button", { name: "移入回收站" }))
  expect(await screen.findByRole("alertdialog", { name: "批量删除失败" })).toHaveTextContent("删除中断")
  expect(screen.getByText("已选 1 个商品")).toBeInTheDocument()
  expect(screen.queryByRole("alertdialog", { name: "已移入回收站" })).not.toBeInTheDocument()
})

test("repeated confirmation cannot send duplicate delete requests", async () => {
  let resolve!: (result: { deleted: number; message: string }) => void
  deleteMock.mockReturnValueOnce(new Promise((onResolve) => { resolve = onResolve }))
  const user = await openPage()
  await user.click(screen.getByRole("checkbox", { name: "选择商品 SKU-1" }))
  await user.click(screen.getByRole("button", { name: "批量删除" }))
  const button = within(screen.getByRole("alertdialog", { name: "确认批量删除" })).getByRole("button", { name: "移入回收站" })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(deleteMock).toHaveBeenCalledOnce()
  await act(async () => resolve({ deleted: 1, message: "已移入回收站 1 条商品" }))
})

test("users without product management permission cannot select or delete all matching products", async () => {
  canManage.value = false
  render(<ProductAdminPage />)
  await screen.findByTestId("card-title-1")
  expect(screen.queryByRole("button", { name: "全选筛选结果" })).not.toBeInTheDocument()
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
  expect(selectionMock).not.toHaveBeenCalled()
})
