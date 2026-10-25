import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"

const { mockListInventory, mockCustomerShops, mockCustomerUnits, mockCustomerBrands, mockInventoryBrands, mockProductCandidates, mockAccountSubjects, mockCreateRecord, mockCreateDetail, mockSuppliers } = vi.hoisted(() => ({
  mockListInventory: vi.fn(), mockCustomerShops: vi.fn(),
  mockCustomerUnits: vi.fn(), mockCustomerBrands: vi.fn(),
  mockInventoryBrands: vi.fn(),
  mockProductCandidates: vi.fn(),
  mockAccountSubjects: vi.fn(),
  mockCreateRecord: vi.fn(),
  mockCreateDetail: vi.fn(),
  mockSuppliers: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, username: "test" } }),
}))

vi.mock("@/components/inventory-admin/inventory-detail-panel", () => ({
  InventoryDetailPanel: () => null,
}))

vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventory: mockListInventory,
  listInventoryBrands: mockInventoryBrands,
  listInventoryDetailCandidates: mockProductCandidates,
  listSuppliers: mockSuppliers,
  listWarehouseBrands: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listGeneralCustomerBrands: mockCustomerBrands,
  listGeneralCustomerShops: mockCustomerShops,
  listGeneralCustomerUnits: mockCustomerUnits,
  listInventoryAccountSubjects: mockAccountSubjects,
  createInventoryRecord: mockCreateRecord,
  createDetail: mockCreateDetail,
}))

let downloadUrls: string[] = []

beforeEach(() => {
  vi.clearAllMocks()
  mockCustomerBrands.mockResolvedValue({ items: [] })
  mockCustomerShops.mockResolvedValue({ items: [] })
  mockCustomerUnits.mockResolvedValue({ items: [] })
  mockInventoryBrands.mockResolvedValue({ items: [] })
  mockProductCandidates.mockResolvedValue({ items: [] })
  mockAccountSubjects.mockResolvedValue({ items: [] })
  mockSuppliers.mockResolvedValue({ items: [] })
  window.localStorage.clear()
  downloadUrls = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    downloadUrls.push(this.href)
  })
  mockListInventory.mockResolvedValue({
    items: [{
      id: 1,
      document_number: "EXPORT-0001",
      document_type: "应付款减少",
      date: "2026-09-03",
      supplier: "测试供应商",
      amount: "1000",
      summary: "质量罚款",
    }],
    total: 30,
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test("keeps all inventory filters accessible and clears unsubmitted changes", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  const filters = within(screen.getByRole("form", { name: "经营历程筛选" }))
  for (const name of ["品牌", "单据类型", "仓库", "客户/供应商", "商品编码"]) {
    expect(filters.getByRole("combobox", { name })).toBeInTheDocument()
  }
  for (const name of ["单据编号", "经手人", "原始货号", "备注"]) {
    expect(filters.getByRole("textbox", { name })).toBeInTheDocument()
  }
  expect(filters.getByRole("button", { name: "清空" })).toBeDisabled()
  await user.type(filters.getByRole("textbox", { name: "单据编号" }), "DRAFT-001")
  expect(filters.getByRole("button", { name: "清空" })).toBeEnabled()
  filters.getByRole("button", { name: "清空" }).focus()
  await user.keyboard("{Enter}")
  expect(filters.getByRole("textbox", { name: "单据编号" })).toHaveValue("")
  expect(filters.getByRole("button", { name: "清空" })).toBeDisabled()
  expect(filters.queryByRole("status")).not.toBeInTheDocument()
})

test("counts applied filter groups and preserves Enter search, refresh and clear", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  const filters = within(screen.getByRole("form", { name: "经营历程筛选" }))
  await user.click(filters.getByRole("button", { name: "日" }))
  await user.type(filters.getByRole("textbox", { name: "经手人" }), "张三{Enter}")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    handler: "张三", date_start: expect.any(String), date_end: expect.any(String),
  })))
  expect(filters.getByRole("status")).toHaveTextContent("已应用 2 项筛选")
  await waitFor(() => expect(filters.getByRole("button", { name: "刷新列表" })).toBeEnabled())
  const requestCount = mockListInventory.mock.calls.length
  await user.click(filters.getByRole("button", { name: "刷新列表" }))
  await waitFor(() => expect(mockListInventory.mock.calls.length).toBeGreaterThan(requestCount))
  expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ handler: "张三" }))
  await user.click(filters.getByRole("button", { name: "清空" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    date_start: undefined, date_end: undefined, handler: undefined,
  })))
  expect(filters.getByRole("textbox", { name: "经手人" })).toHaveValue("")
  expect(filters.queryByRole("status")).not.toBeInTheDocument()
})

test("keeps the shared purchase filters in purchase mode", async () => {
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("EXPORT-0001")
  const filters = within(screen.getByRole("form", { name: "采购单筛选" }))
  expect(filters.getByRole("combobox", { name: "客户/供应商" })).toBeInTheDocument()
  expect(filters.getByRole("textbox", { name: "单据编号" })).toBeInTheDocument()
  expect(filters.getByRole("textbox", { name: "货号" })).toBeInTheDocument()
  expect(filters.queryByRole("combobox", { name: "品牌" })).not.toBeInTheDocument()
  expect(filters.getByRole("button", { name: "清空" })).toBeDisabled()
})

test.each(["inventory", "purchase-orders"] as const)("accepts multiple typed handlers and preserves the submitted %s export scope", async (mode) => {
  const user = userEvent.setup()
  const first = render(<InventoryPage mode={mode} />)
  await screen.findByText("EXPORT-0001")
  const input = screen.getByRole("textbox", { name: "经手人" })
  expect(input).toHaveAttribute("placeholder", "姓名，多个用逗号分隔")
  expect(input).toHaveAttribute("rows", "1")
  expect(input).toHaveAccessibleDescription(/匹配任意一人/)
  const requestCount = mockListInventory.mock.calls.length
  await user.type(input, "张三，李四;王五{Shift>}{Enter}{/Shift}赵六")
  const handlers = "张三，李四;王五\n赵六"
  expect(input).toHaveValue(handlers)
  expect(input).toHaveAttribute("rows", "2")
  expect(mockListInventory).toHaveBeenCalledTimes(requestCount)
  await user.keyboard("{Enter}")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    handler: handlers,
    page: 1,
    document_type: mode === "purchase-orders" ? "进货订单" : undefined,
    exclude_document_type: mode === "inventory" ? "进货订单" : undefined,
  })))
  expect(screen.getByRole("status")).toHaveTextContent("已应用 1 项筛选")

  await user.type(input, "，未提交")
  const exportNames = mode === "purchase-orders" ? ["汇总导出", "尺码明细导出", "生产采购单导出"] : ["导出Excel"]
  for (const name of exportNames) {
    const exportButton = screen.getByRole("button", { name })
    await waitFor(() => expect(exportButton).toBeEnabled())
    await user.click(exportButton)
    expect(new URL(downloadUrls.at(-1)!).searchParams.get("handler")).toBe(handlers)
  }

  first.unmount()
  render(<InventoryPage mode={mode} />)
  await screen.findByText("EXPORT-0001")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ handler: handlers })))
  expect(screen.getByRole("textbox", { name: "经手人" })).toHaveValue(`${handlers}，未提交`)
  await user.click(screen.getByRole("button", { name: "清空" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ handler: undefined })))
  expect(screen.getByRole("textbox", { name: "经手人" })).toHaveValue("")
})

test("allows pasting multiple handler lines without submitting during composition", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  const input = screen.getByRole("textbox", { name: "经手人" })
  await user.click(input)
  await user.paste("张三\n李四\n王五\n赵六")
  expect(input).toHaveAttribute("rows", "3")
  const requestCount = mockListInventory.mock.calls.length
  fireEvent.keyDown(input, { key: "Enter", code: "Enter", isComposing: true })
  expect(mockListInventory).toHaveBeenCalledTimes(requestCount)
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ handler: "张三\n李四\n王五\n赵六" })))
})

test("exports all filtered fine records rather than only the visible page", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  await user.type(screen.getByPlaceholderText("摘要/备注"), "罚款")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    summary: "罚款", completion_status: "completed", exclude_document_type: "进货订单",
  })))
  const exportButton = screen.getByRole("button", { name: "导出Excel" })
  await waitFor(() => expect(exportButton).toBeEnabled())
  await user.click(exportButton)

  expect(downloadUrls).toHaveLength(1)
  const params = new URL(downloadUrls[0]).searchParams
  expect(params.get("summary")).toBe("罚款")
  expect(params.get("completion_status")).toBe("completed")
  expect(params.get("exclude_document_type")).toBe("进货订单")
  expect(params.has("document_type")).toBe(false)
  expect(params.has("ids")).toBe(false)
  expect(params.has("page")).toBe(false)
})

test.each([true, false])("searches and exports product codes with candidate selection=%s", async (selectCandidate) => {
  mockProductCandidates.mockResolvedValue({ items: [{
    product_code: "QT653891S73", sku: "QT653891S73", original_sku: "QT653891",
    product_name: "休闲鞋", color_name: "黑色", factory_code: "", brand: "cbanner_mens",
  }] })
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  const input = screen.getByRole("combobox", { name: "商品编码" })
  await user.type(input, "QT65")
  const option = await screen.findByRole("button", { name: "QT653891S73" })
  expect(mockProductCandidates).toHaveBeenLastCalledWith({ query: "QT65", limit: 20 })
  const productCode = selectCandidate ? "QT653891S73" : "QT65"
  if (selectCandidate) {
    await user.click(option)
    await user.click(screen.getByRole("button", { name: "搜索" }))
  } else {
    await user.keyboard("{Enter}")
  }
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ product_code: productCode })))
  expect(input).toHaveValue(productCode)
  const exportButton = screen.getByRole("button", { name: "导出Excel" })
  await waitFor(() => expect(exportButton).toBeEnabled())
  await user.click(exportButton)
  expect(downloadUrls).toHaveLength(1)
  expect(new URL(downloadUrls[0]).searchParams.get("product_code")).toBe(productCode)
})

test("excludes disabled shops and their units from new customer business options", async () => {
  mockCustomerBrands.mockResolvedValue({ items: [{ id: 1, name: "客户品牌" }] })
  mockCustomerShops.mockResolvedValue({ items: [
    { id: 1, customer_name: "客户品牌", shop_name: "启用店铺", is_active: true },
    { id: 2, customer_name: "客户品牌", shop_name: "停用店铺", is_active: false },
  ] })
  mockCustomerUnits.mockResolvedValue({ items: [
    { id: 1, shop_id: 1, unit_name: "启用单位" },
    { id: 2, shop_id: 2, unit_name: "停用单位" },
  ] })
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  await user.click(screen.getByRole("button", { name: "新增经营历程" }))
  const dialog = screen.getByRole("dialog")
  await user.selectOptions(within(dialog).getByRole("combobox"), "批发销售单")
  const customerInput = within(dialog).getByPlaceholderText("选择品牌后选收货客户")
  await user.type(customerInput, "停用")
  expect(within(dialog).getByText("没有可选项")).toBeInTheDocument()
  await user.clear(customerInput)
  await user.type(customerInput, "启用")
  expect(within(dialog).getByRole("button", { name: "客户品牌 / 启用店铺" })).toBeInTheDocument()
  expect(within(dialog).getByRole("button", { name: "客户品牌 / 启用店铺 / 启用单位" })).toBeInTheDocument()
})

test("creates a record with an accounting subject from the searchable grouped dropdown", async () => {
  mockAccountSubjects.mockResolvedValue({ items: [
    { id: 1, name: "大底收入", category: "收入类" },
    { id: 2, name: "包装费用", category: "支出类" },
  ] })
  mockCreateRecord.mockResolvedValue({ item: { id: 22 } })
  mockCreateDetail.mockResolvedValue({ item: { id: 23 } })
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  await user.click(screen.getByRole("button", { name: "新增经营历程" }))
  const dialog = screen.getByRole("dialog", { name: "新增经营历程" })
  await user.selectOptions(within(dialog).getByRole("combobox"), "应付款减少")
  await user.type(within(dialog).getByLabelText("减少金额"), "268.5")
  await user.type(within(dialog).getByLabelText("明细备注"), "包装调整")
  await user.click(within(dialog).getByLabelText("费用项目名 / 科目"))
  await user.type(within(dialog).getByRole("combobox", { name: "搜索科目" }), "包装")
  await user.click(within(dialog).getByRole("option", { name: "包装费用" }))
  expect(within(dialog).getByLabelText("减少金额")).toHaveValue(268.5)
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() => expect(mockCreateRecord).toHaveBeenCalledWith(expect.objectContaining({ document_type: "应付款减少" })))
  await waitFor(() => expect(mockCreateDetail).toHaveBeenCalledWith(22, {
    product_code: "",
    product_name: "包装费用",
    amount: "268.5",
    remark: "包装调整",
  }))
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "新增经营历程" })).not.toBeInTheDocument())
})

test("searches and exports using unified supplier and customer brand options without warehouses", async () => {
  mockInventoryBrands.mockResolvedValue({ items: [
    { value: "yandou", label: "烟斗" },
    { value: "custom", label: "自定义品牌" },
  ] })
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  await user.click(screen.getByPlaceholderText("选择品牌"))
  await user.click(await screen.findByRole("button", { name: "烟斗" }))
  await user.click(await screen.findByRole("button", { name: "自定义品牌" }))
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    brands: ["yandou", "custom"], completion_status: "completed",
  })))
  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  expect(new URL(downloadUrls[0]).searchParams.getAll("brands")).toEqual(["yandou", "custom"])
})

test.each(["inventory", "purchase-orders"] as const)("shows new supplier brand names rather than internal codes in %s creation and import controls", async (mode) => {
  const brandCode = "supplier_brand_33aa8a0c3b6a"
  mockInventoryBrands.mockResolvedValue({ items: [{ value: brandCode, label: "千百度赫锦" }] })
  mockSuppliers.mockResolvedValue({ items: [{ id: 1676, brand: brandCode, name: "靓典（千百度赫锦）" }] })
  const user = userEvent.setup()
  render(<InventoryPage mode={mode} />)
  await screen.findByText("EXPORT-0001")
  if (mode === "inventory") {
    await user.click(screen.getByRole("combobox", { name: "品牌" }))
    await user.click(await screen.findByRole("button", { name: "千百度赫锦" }))
    await user.click(screen.getByRole("button", { name: "搜索" }))
    await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ brands: [brandCode] })))
  }
  await user.click(screen.getByRole("button", { name: mode === "inventory" ? "新增经营历程" : "新增采购单" }))
  const dialog = screen.getByRole("dialog", { name: mode === "inventory" ? "新增经营历程" : "新增采购单" })
  const supplier = within(dialog).getByPlaceholderText("选择品牌后选供应商")
  await user.click(supplier)
  await user.click(await within(dialog).findByRole("button", { name: "千百度赫锦" }))
  await user.click(within(dialog).getByRole("button", { name: "靓典（千百度赫锦）" }))
  expect(supplier).toHaveValue("千百度赫锦 / 靓典（千百度赫锦）")
  expect(within(dialog).queryByText(brandCode)).not.toBeInTheDocument()
  await user.click(within(dialog).getByRole("button", { name: "取消" }))
  if (mode === "purchase-orders") return
  await user.click(screen.getByRole("button", { name: "导入Excel" }))
  const importDialog = screen.getByRole("dialog", { name: "导入单据明细" })
  await user.click(within(importDialog).getByRole("button", { name: "按模板导入" }))
  const fallbackBrand = within(importDialog).getByRole("combobox", { name: "备用品牌" })
  await user.selectOptions(fallbackBrand, brandCode)
  expect(fallbackBrand).toHaveValue(brandCode)
  expect(within(fallbackBrand).getByRole("option", { name: "千百度赫锦" })).toBeInTheDocument()
  await user.click(within(importDialog).getByRole("button", { name: "普通导入" }))
  const importSupplier = within(importDialog).getByPlaceholderText("选择品牌后选供货单位")
  await user.type(importSupplier, "赫锦")
  expect(within(importDialog).getByRole("button", { name: "千百度赫锦 / 靓典（千百度赫锦）" })).toBeInTheDocument()
  expect(within(importDialog).queryByText(brandCode)).not.toBeInTheDocument()
})

test("restores inventory filters after another page and keeps purchase queries isolated", async () => {
  const user = userEvent.setup()
  const first = render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")
  await user.type(screen.getByPlaceholderText("输入单据编号"), "KEEP-123")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ document_number: "KEEP-123" })))
  first.unmount()

  const purchase = render(<InventoryPage mode="purchase-orders" />)
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ document_type: "进货订单", document_number: undefined })))
  expect(screen.getByRole("textbox", { name: "单据编号" })).toHaveValue("")
  await user.type(screen.getByRole("textbox", { name: "单据编号" }), "PURCHASE-456{Enter}")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ document_type: "进货订单", document_number: "PURCHASE-456" })))
  purchase.unmount()

  const restored = render(<InventoryPage />)
  expect(screen.getByPlaceholderText("输入单据编号")).toHaveValue("KEEP-123")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ document_number: "KEEP-123" })))
  await user.click(screen.getByRole("button", { name: "清空" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ document_number: undefined })))
  restored.unmount()

  const restoredPurchase = render(<InventoryPage mode="purchase-orders" />)
  expect(screen.getByRole("textbox", { name: "单据编号" })).toHaveValue("PURCHASE-456")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ document_type: "进货订单", document_number: "PURCHASE-456" })))
  restoredPurchase.unmount()

  render(<InventoryPage />)
  expect(screen.getByPlaceholderText("输入单据编号")).toHaveValue("")
  await screen.findByText("EXPORT-0001")
})

test.each(["button", "enter"])("filters purchase document numbers through %s, paginates and exports all modes", async (submitMode) => {
  const user = userEvent.setup()
  render(<InventoryPage mode="purchase-orders" />)
  await screen.findByText("EXPORT-0001")
  const filters = within(screen.getByRole("form", { name: "采购单筛选" }))

  await user.click(screen.getByText("下一页"))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
  const callsBeforeTyping = mockListInventory.mock.calls.length
  const input = filters.getByRole("textbox", { name: "单据编号" })
  await user.type(input, "  JHDD-2026-0001  ")
  expect(mockListInventory).toHaveBeenCalledTimes(callsBeforeTyping)
  expect(filters.getByRole("button", { name: "清空" })).toBeEnabled()
  if (submitMode === "button") {
    await user.click(filters.getByRole("button", { name: "搜索" }))
  } else {
    await user.keyboard("{Enter}")
  }
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: "JHDD-2026-0001", document_type: "进货订单", page: 1,
  })))
  expect(filters.getByRole("status")).toHaveTextContent("已应用 1 项筛选")

  await user.click(screen.getByText("下一页"))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: "JHDD-2026-0001", document_type: "进货订单", page: 2,
  })))

  await user.clear(input)
  await user.type(input, "UNSUBMITTED")
  const exportModes = [
    { label: "汇总导出", mode: "summary" },
    { label: "尺码明细导出", mode: "size_rows" },
    { label: "生产采购单导出", mode: "production_order" },
  ]
  for (const [index, exportMode] of exportModes.entries()) {
    const exportButton = screen.getByRole("button", { name: exportMode.label })
    await waitFor(() => expect(exportButton).toBeEnabled())
    await user.click(exportButton)
    const params = new URL(downloadUrls[index]).searchParams
    expect(params.get("document_number")).toBe("JHDD-2026-0001")
    expect(params.get("document_type")).toBe("进货订单")
    expect(params.get("purchase_export_mode")).toBe(exportMode.mode)
    expect(params.has("page")).toBe(false)
  }
  expect(downloadUrls).toHaveLength(exportModes.length)

  await user.click(filters.getByRole("button", { name: "清空" }))
  expect(input).toHaveValue("")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: undefined, document_type: "进货订单", page: 1,
  })))
  expect(filters.queryByRole("status")).not.toBeInTheDocument()
  expect(filters.getByRole("button", { name: "清空" })).toBeDisabled()
})

test("searches and exports by document number, then clears the filter", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  await screen.findByText("EXPORT-0001")

  await user.type(screen.getByPlaceholderText("输入单据编号"), "0001")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: "0001", exclude_document_type: "进货订单",
  })))

  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  expect(new URL(downloadUrls[0]).searchParams.get("document_number")).toBe("0001")

  await user.click(screen.getByRole("button", { name: "清空" }))
  expect(screen.getByPlaceholderText("输入单据编号")).toHaveValue("")
  await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
    document_number: undefined,
  })))
})

test.each(["应付款减少", "应付款增加", "应收款减少", "应收款增加"])(
  "allows exporting when %s is the selected document type",
  async (documentType) => {
    const user = userEvent.setup()
    render(<InventoryPage />)
    await screen.findByText("EXPORT-0001")
    await user.click(screen.getByPlaceholderText("选择单据类型"))
    await user.click(screen.getByRole("button", { name: documentType }))
    await user.click(screen.getByRole("button", { name: "搜索" }))
    await waitFor(() => expect(mockListInventory).toHaveBeenLastCalledWith(expect.objectContaining({
      document_types: [documentType],
    })))
    const exportButton = screen.getByRole("button", { name: "导出Excel" })
    await waitFor(() => expect(exportButton).toBeEnabled())
    await user.click(exportButton)

    expect(downloadUrls).toHaveLength(1)
    expect(new URL(downloadUrls[0]).searchParams.getAll("document_types")).toEqual([documentType])
    expect(screen.queryByText("暂不支持导出")).not.toBeInTheDocument()
  },
)

test("exports selected accounting documents by ID", async () => {
  const user = userEvent.setup()
  render(<InventoryPage />)
  const documentNumber = await screen.findByText("EXPORT-0001")
  const row = documentNumber.closest("tr")!
  await user.click(within(row).getByRole("checkbox"))
  await user.click(screen.getByRole("button", { name: "导出Excel" }))

  expect(downloadUrls).toHaveLength(1)
  expect(new URL(downloadUrls[0]).searchParams.get("ids")).toBe("1")
})

test("aligns inventory totals with their table headers", async () => {
  mockListInventory.mockResolvedValueOnce({
    items: [{ id: 1, document_number: "ALIGN-0001", document_type: "进货单", date: "2026-09-03", total_count: "5", amount: "100" }],
    total: 1,
    totals: {
      current_page: { total_count: "5", amount: "100" },
      all: { total_count: "50", amount: "1000" },
    },
  })
  render(<InventoryPage />)
  await screen.findByText("ALIGN-0001")

  const table = screen.getByText("ALIGN-0001").closest("table")!
  const headers = Array.from(table.querySelectorAll("thead th"))
  const rows = Array.from(table.querySelectorAll("tfoot tr"))
  expect(rows).toHaveLength(2)
  for (const [rowIndex, values] of [["5", "100"], ["50", "1000"]].entries()) {
    const cells = Array.from(rows[rowIndex].querySelectorAll("td"))
    expect(cells).toHaveLength(headers.length)
    expect(cells[headers.findIndex((header) => header.textContent?.includes("总数"))]).toHaveTextContent(values[0])
    expect(cells[headers.findIndex((header) => header.textContent?.includes("金额"))]).toHaveTextContent(values[1])
  }
})

test("keeps totals under their headers after dragging amount and count", async () => {
  mockListInventory.mockResolvedValueOnce({
    items: [{ id: 1, document_number: "ALIGN-0002", document_type: "进货单", date: "2026-09-03", total_count: "5", amount: "100" }],
    total: 1,
    totals: {
      current_page: { total_count: "5", amount: "100" },
      all: { total_count: "50", amount: "1000" },
    },
  })
  render(<InventoryPage />)
  await screen.findByText("ALIGN-0002")

  const table = screen.getByText("ALIGN-0002").closest("table")!
  const dataTransfer = {
    effectAllowed: "move",
    dropEffect: "move",
    setData: vi.fn(),
    getData: vi.fn(() => "amount"),
  }
  fireEvent.dragStart(screen.getByRole("button", { name: "拖拽排序金额" }), { dataTransfer })
  fireEvent.dragOver(screen.getByRole("button", { name: "拖拽排序日期" }).closest("th")!, { dataTransfer })
  fireEvent.drop(screen.getByRole("button", { name: "拖拽排序日期" }).closest("th")!, { dataTransfer })

  const headers = Array.from(table.querySelectorAll("thead th"))
  const totalRows = Array.from(table.querySelectorAll("tfoot tr"))
  const bodyCells = Array.from(table.querySelector("tbody tr")!.querySelectorAll("td"))
  const amountIndex = headers.findIndex((header) => header.textContent?.includes("金额"))
  const countIndex = headers.findIndex((header) => header.textContent?.includes("总数"))
  expect(amountIndex).toBe(2)
  expect(bodyCells[amountIndex]).toHaveTextContent("100")
  expect(bodyCells[countIndex]).toHaveTextContent("5")
  for (const [rowIndex, values] of [["100", "5"], ["1000", "50"]].entries()) {
    const cells = Array.from(totalRows[rowIndex].querySelectorAll("td"))
    expect(cells).toHaveLength(headers.length)
    expect(cells[amountIndex]).toHaveTextContent(values[0])
    expect(cells[countIndex]).toHaveTextContent(values[1])
  }

  dataTransfer.getData.mockReturnValue("total_count")
  fireEvent.dragStart(screen.getByRole("button", { name: "拖拽排序总数" }), { dataTransfer })
  fireEvent.drop(screen.getByRole("button", { name: "拖拽排序单据编号" }).closest("th")!, { dataTransfer })

  const reorderedHeaders = Array.from(table.querySelectorAll("thead th"))
  const reorderedCountIndex = reorderedHeaders.findIndex((header) => header.textContent?.includes("总数"))
  const reorderedAmountIndex = reorderedHeaders.findIndex((header) => header.textContent?.includes("金额"))
  expect(reorderedCountIndex).toBe(1)
  for (const [rowIndex, values] of [["5", "100"], ["50", "1000"]].entries()) {
    const cells = Array.from(totalRows[rowIndex].querySelectorAll("td"))
    expect(cells[reorderedCountIndex]).toHaveTextContent(values[0])
    expect(cells[reorderedAmountIndex]).toHaveTextContent(values[1])
  }
})
