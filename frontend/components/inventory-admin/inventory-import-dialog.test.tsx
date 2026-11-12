import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryPage } from "@/components/inventory-admin/inventory-page"
import { InventoryImportUpload } from "@/components/inventory-admin/inventory-import-upload"
import { INVENTORY_IMPORT_MAX_FILE_BYTES } from "@/lib/upload-limits.mjs"
import {
  ApiError,
  type InventoryImportTask,
  type InventoryTemplatePreview,
  type PurchaseImportPreview,
} from "@/lib/api"

const {
  listInventoryMock,
  previewTemplateMock,
  importTemplateMock,
  getTaskMock,
  previewPurchaseMock,
  importPurchaseMock,
  purchaseTaskMock,
  getPurchaseTaskMock,
  resolveMissingTaskMock,
} = vi.hoisted(() => ({
  listInventoryMock: vi.fn(),
  previewTemplateMock: vi.fn(),
  importTemplateMock: vi.fn(),
  getTaskMock: vi.fn(),
  previewPurchaseMock: vi.fn(),
  importPurchaseMock: vi.fn(),
  purchaseTaskMock: vi.fn(),
  getPurchaseTaskMock: vi.fn(),
  resolveMissingTaskMock: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, username: "测试用户" } }),
}))
vi.mock("@/components/inventory-admin/inventory-detail-panel", () => ({
  InventoryDetailPanel: () => null,
}))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventory: listInventoryMock,
  listInventoryBrands: async () => ({ items: [] }),
  listSuppliers: async () => ({ items: [] }),
  listWarehouseBrands: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listGeneralCustomerBrands: async () => ({ items: [] }),
  listGeneralCustomerShops: async () => ({ items: [] }),
  listGeneralCustomerUnits: async () => ({ items: [] }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
  previewInventoryTemplate: previewTemplateMock,
  submitInventoryTemplateTask: importTemplateMock,
  getInventoryTemplateTask: getTaskMock,
  previewPurchaseInventory: previewPurchaseMock,
  importPurchaseInventory: importPurchaseMock,
  submitPurchaseImportTask: purchaseTaskMock,
  getPurchaseImportTask: getPurchaseTaskMock,
  resolveMissingImportTask: resolveMissingTaskMock,
}))

const templatePreview: InventoryTemplatePreview = {
  kind: "purchase",
  total: 2,
  conflicts: [],
  brand_by_key: { first: "cbanner_mens", second: "cbanner_mens" },
  brand_sources: {},
  unresolved_brand_keys: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  window.sessionStorage.clear()
  listInventoryMock.mockResolvedValue({ items: [], total: 0 })
  previewTemplateMock.mockResolvedValue(templatePreview)
  importTemplateMock.mockImplementation(async (payload) => ({
    task_id: payload.taskId,
    filename: payload.file.name,
    status: "succeeded",
    result: {
      created: 2,
      replaced: 0,
      skipped: 0,
      details: 2,
      message: "成功导入 2 张单据",
    },
    error: null,
    error_status: null,
  }))
  getTaskMock.mockResolvedValue({
    task_id: "a".repeat(32),
    filename: "进货单.xlsx",
    status: "succeeded",
    result: {
      created: 2,
      replaced: 0,
      skipped: 0,
      details: 2,
      message: "成功导入 2 张单据",
    },
    error: null,
    error_status: null,
  })
  previewPurchaseMock.mockResolvedValue({ total: 1, conflicts: [] })
  importPurchaseMock.mockResolvedValue({ message: "成功导入采购单" })
  purchaseTaskMock.mockImplementation(async (payload) => payload.preview
    ? { ...importTask("succeeded", payload.taskId), filename: payload.file.name, result: null, preview: { total: 1, conflicts: [] } }
    : { ...importTask("succeeded", payload.taskId), filename: payload.file.name })
  getPurchaseTaskMock.mockImplementation(getTaskMock)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function openImport(
  mode: "inventory" | "purchase-orders" = "inventory",
  template = true
) {
  const user = userEvent.setup()
  render(<InventoryPage mode={mode} />)
  await waitFor(() => expect(listInventoryMock).toHaveBeenCalled())
  await user.click(
    screen.getByRole("button", {
      name: mode === "purchase-orders" ? "导入采购单" : "导入Excel",
    })
  )
  const dialog = screen.getByRole("dialog", {
    name: mode === "purchase-orders" ? "导入采购单" : "导入单据明细",
  })
  if (template && mode === "inventory")
    await user.click(within(dialog).getByRole("button", { name: "按模板导入" }))
  return { user, dialog, ui: within(dialog) }
}

function selectFile(dialog: HTMLElement, name = "进货单.xlsx", size?: number) {
  const file = new File(["excel"], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  })
  if (size !== undefined) Object.defineProperty(file, "size", { value: size })
  fireEvent.change(within(dialog).getByLabelText("Excel 文件"), {
    target: { files: [file] },
  })
  return file
}

test("groups eight template downloads and keeps precheck disabled until a file is selected", async () => {
  const { ui } = await openImport()
  expect(ui.getByRole("group", { name: "导入方式" })).toBeInTheDocument()
  expect(ui.getByRole("button", { name: "按模板导入" })).toHaveAttribute(
    "aria-pressed",
    "true"
  )
  const templates = within(ui.getByRole("region", { name: "下载导入模板" }))
  expect(templates.getAllByRole("button")).toHaveLength(8)
  expect(ui.getByRole("combobox", { name: "备用品牌" })).toHaveValue("")
  expect(ui.getByText("单个文件不超过 100MB")).toBeInTheDocument()
  expect(ui.getByRole("button", { name: "预检查" })).toBeDisabled()
  expect(ui.getByRole("status")).toHaveTextContent("选择 Excel 文件后开始检查")
})

test("downloads each original template URL without submitting an import", async () => {
  const downloads: string[] = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement
  ) {
    downloads.push(this.getAttribute("href") || "")
  })
  const { user, ui } = await openImport()
  const labels = [
    "进货单",
    "进货退货单",
    "销售单",
    "销售退货单",
    "报损单",
    "报溢单",
    "同价调拨单",
    "应收应付",
  ]
  for (const label of labels)
    await user.click(ui.getByRole("button", { name: "下载" + label + "模板" }))
  expect(downloads).toEqual(
    [
      "purchase",
      "purchase_return",
      "sale",
      "sale_return",
      "stock_loss",
      "stock_gain",
      "transfer",
      "accounting",
    ].map((kind) => "/api/inventory/import-template/download/" + kind)
  )
  expect(importTemplateMock).not.toHaveBeenCalled()
})

test("prechecks a selected file before confirming the template import", async () => {
  const { user, dialog, ui } = await openImport()
  const file = selectFile(dialog)
  expect(ui.getByText(file.name)).toBeInTheDocument()
  expect(
    ui.getByRole("button", { name: "更换 Excel 文件" })
  ).toBeInTheDocument()
  await user.selectOptions(
    ui.getByRole("combobox", { name: "备用品牌" }),
    "cbanner_mens"
  )
  await user.click(ui.getByRole("button", { name: "预检查" }))
  expect(previewTemplateMock).toHaveBeenCalledWith(file)
  expect(importTemplateMock).not.toHaveBeenCalled()
  expect(await ui.findByRole("button", { name: "确认导入" })).toBeEnabled()
  expect(ui.getByRole("status")).toHaveTextContent("预检查完成")
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(importTemplateMock).toHaveBeenCalledWith({
    taskId: expect.stringMatching(/^[a-f0-9]{32}$/),
    file,
    brand: "cbanner_mens",
    decisions: {},
  })
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "导入单据明细" })
    ).not.toBeInTheDocument()
  )
})

test("preserves conflict decisions and prevents import until they are resolved", async () => {
  previewTemplateMock.mockResolvedValueOnce({
    ...templatePreview,
    conflicts: [
      {
        key: "first",
        date: "2026-10-16",
        summary: "重复摘要",
        document_type: "进货单",
        existing_number: "JH-001",
        can_merge: true,
      },
    ],
  })
  const { user, dialog, ui } = await openImport()
  const file = selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  await ui.findByRole("button", { name: "确认导入" })
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(ui.getByRole("alert")).toHaveTextContent("选择覆盖、新增或取消该单据")
  expect(importTemplateMock).not.toHaveBeenCalled()
  const choice = ui
    .getAllByRole("combobox")
    .find((element) =>
      within(element).queryByRole("option", { name: "请选择处理方式" })
    )!
  await user.selectOptions(choice, "new")
  const summary = ui.getByPlaceholderText("请输入不同于原摘要的新摘要")
  await user.type(summary, "独立摘要")
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(importTemplateMock).toHaveBeenCalledWith({
    taskId: expect.stringMatching(/^[a-f0-9]{32}$/),
    file,
    brand: expect.any(String),
    decisions: { first: { action: "new", new_summary: "独立摘要" } },
  })
})

test("requires a fallback brand when the preview cannot identify it", async () => {
  previewTemplateMock.mockResolvedValueOnce({
    ...templatePreview,
    brand_by_key: {},
    unresolved_brand_keys: ["first"],
  })
  const { user, dialog, ui } = await openImport()
  selectFile(dialog)
  await user.selectOptions(ui.getByRole("combobox", { name: "备用品牌" }), "")
  await user.click(ui.getByRole("button", { name: "预检查" }))
  await ui.findByRole("button", { name: "确认导入" })
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(ui.getByRole("alert")).toHaveTextContent("请选择品牌")
  expect(importTemplateMock).not.toHaveBeenCalled()
  await user.selectOptions(
    ui.getByRole("combobox", { name: "备用品牌" }),
    "cbanner_mens"
  )
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(importTemplateMock).toHaveBeenCalledWith(
    expect.objectContaining({ brand: "cbanner_mens" })
  )
})

test("removing or replacing a file invalidates its preview", async () => {
  const { user, dialog, ui } = await openImport()
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  await ui.findByRole("button", { name: "确认导入" })
  const replacement = selectFile(dialog, "替换.xlsm")
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
  expect(ui.queryByRole("button", { name: "确认导入" })).not.toBeInTheDocument()
  await user.click(ui.getByRole("button", { name: "预检查" }))
  expect(previewTemplateMock).toHaveBeenLastCalledWith(replacement)
  await ui.findByRole("button", { name: "确认导入" })
  await user.click(ui.getByRole("button", { name: "移除已选文件" }))
  expect(ui.getByRole("button", { name: "预检查" })).toBeDisabled()
  expect(
    ui.getByRole("button", { name: "选择 Excel 文件" })
  ).toBeInTheDocument()
})

test("switching modes clears the old upload but clicking the selected mode preserves it", async () => {
  const { user, dialog, ui } = await openImport()
  const file = selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "按模板导入" }))
  expect(ui.getByText(file.name)).toBeInTheDocument()
  await user.click(ui.getByRole("button", { name: "普通导入" }))
  expect(ui.queryByText(file.name)).not.toBeInTheDocument()
  expect(
    ui.getByRole("button", { name: "选择 Excel 文件" })
  ).toBeInTheDocument()
  await user.click(ui.getByRole("button", { name: "按模板导入" }))
  expect(ui.getByRole("button", { name: "预检查" })).toBeDisabled()
})

test.each([
  ["数据.csv", undefined, "仅支持 .xlsx、.xls 或 .xlsm 格式的 Excel 文件"],
  [
    "过大.xlsx",
    INVENTORY_IMPORT_MAX_FILE_BYTES + 1,
    "导入文件不能超过 100MB，请拆分 Excel 后重试",
  ],
] as const)(
  "rejects invalid upload %s before any request",
  async (name, size, message) => {
    const { dialog, ui } = await openImport()
    selectFile(dialog, name, size)
    expect(ui.getByRole("alert")).toHaveTextContent(message)
    expect(ui.getByRole("button", { name: "预检查" })).toBeDisabled()
    expect(previewTemplateMock).not.toHaveBeenCalled()
  }
)

test("accepts a 100MB boundary file and shows its size", async () => {
  const { dialog, ui } = await openImport()
  selectFile(dialog, "边界.xlsx", INVENTORY_IMPORT_MAX_FILE_BYTES)
  expect(ui.getByText("100.00 MB")).toBeInTheDocument()
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
})

test("supports drag and drop in template mode", async () => {
  const { ui } = await openImport()
  const file = new File(["excel"], "拖入.XLSX")
  const target = ui.getByRole("button", { name: "选择 Excel 文件" })
  const dataTransfer = { files: [file], types: ["Files"] }
  fireEvent.dragEnter(target, { dataTransfer })
  expect(ui.getByText("松开即可添加文件")).toBeInTheDocument()
  fireEvent.drop(target, { dataTransfer })
  expect(ui.getByText(file.name)).toBeInTheDocument()
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
})

test("locks changes and closing while prechecking, then displays a recoverable error", async () => {
  let rejectPreview!: (error: Error) => void
  previewTemplateMock.mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        rejectPreview = reject
      })
  )
  const { user, dialog, ui } = await openImport()
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  expect(ui.getByRole("button", { name: "处理中..." })).toBeDisabled()
  expect(ui.getByRole("button", { name: "关闭" })).toBeDisabled()
  expect(ui.getByRole("button", { name: "普通导入" })).toBeDisabled()
  expect(ui.getByRole("combobox", { name: "备用品牌" })).toBeDisabled()
  expect(ui.getByRole("button", { name: "移除已选文件" })).toBeDisabled()
  fireEvent.keyDown(dialog, { key: "Escape" })
  expect(dialog).toBeInTheDocument()
  await act(async () => rejectPreview(new Error("模板格式不正确")))
  expect(await ui.findByRole("alert")).toHaveTextContent("模板格式不正确")
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
  expect(ui.getByRole("button", { name: "关闭" })).toBeEnabled()
})

test("shows unmatched product codes separately and copies them without submitting an import", async () => {
  previewTemplateMock.mockRejectedValueOnce(new ApiError(400,
    "以下商品编码未匹配到商品信息档案：C2153112DF8080255、AS861182D020235。请联系商品部维护商品信息档案后再导入；本次未导入任何数据。"
  ))
  const { user, dialog, ui } = await openImport()
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  const file = selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  const alert = within(await ui.findByRole("alert"))
  expect(alert.getByText("商品档案未匹配")).toBeInTheDocument()
  expect(alert.getByText("本次未导入任何数据，请先核对以下商品。")).toBeInTheDocument()
  expect(within(alert.getByRole("list", { name: "未匹配的商品编码" })).getAllByRole("listitem")).toHaveLength(2)
  await user.click(alert.getByRole("button", { name: "复制编码" }))
  expect(writeText).toHaveBeenCalledWith("C2153112DF8080255\nAS861182D020235")
  expect(alert.getByRole("button", { name: "已复制" })).toHaveFocus()
  expect(ui.getByText(file.name)).toBeInTheDocument()
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
  expect(importTemplateMock).not.toHaveBeenCalled()
  selectFile(dialog, "修正后.xlsx")
  expect(ui.queryByRole("alert")).not.toBeInTheDocument()
})

const productValidation = {
  code: "product_validation" as const, message: "发现 2 条商品资料错误，请联系商品部；本次未导入任何数据。", total: 2,
  errors: [2, 8].map((row) => ({ row_number: row, product_code: `000SKU${row}`, brand: "ni", summary: `单据${row}`, reason: "未匹配到商品信息档案" })),
}

test("template precheck shows the complete structured list and changing file clears it", async () => {
  previewTemplateMock.mockRejectedValueOnce(new ApiError(400, productValidation))
  const { user, dialog, ui } = await openImport()
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  expect(await ui.findByRole("region", { name: "商品资料错误明细" })).toBeInTheDocument()
  expect(ui.getByText("000SKU8")).toBeInTheDocument()
  expect(importTemplateMock).not.toHaveBeenCalled()
  selectFile(dialog, "修正.xlsx")
  expect(ui.queryByRole("region", { name: "商品资料错误明细" })).not.toBeInTheDocument()
})

test.each(["inventory", "purchase-orders"] as const)("%s failed background task shows all persisted product issues and unlocks retry", async (mode) => {
  const task = { task_id: "a".repeat(32), filename: "错误.xlsx", status: "failed", result: null,
    error: productValidation.message + "（批次编号：" + "a".repeat(32) + "）", error_status: 400, validation: productValidation }
  if (mode === "inventory") importTemplateMock.mockResolvedValueOnce(task)
  else purchaseTaskMock.mockResolvedValueOnce(task)
  const { user, dialog, ui } = await openImport(mode)
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  if (mode === "inventory") await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(await ui.findByRole("region", { name: "商品资料错误明细" })).toBeInTheDocument()
  expect(ui.getByText("000SKU8")).toBeInTheDocument()
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
})

test("identifies a truncated code list and does not claim to copy undisplayed codes", async () => {
  previewTemplateMock.mockRejectedValueOnce(new Error(
    "以下商品编码未匹配到商品信息档案：SKU-01、SKU-02等 25 个商品编码。请联系商品部维护商品信息档案后再导入；本次未导入任何数据。"
  ))
  const { user, dialog, ui } = await openImport()
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  const alert = within(await ui.findByRole("alert"))
  expect(alert.getByText("仅显示前 2 个编码，共 25 个未匹配。")).toBeInTheDocument()
  await user.click(alert.getByRole("button", { name: "复制已显示编码" }))
  expect(writeText).toHaveBeenCalledWith("SKU-01\nSKU-02")
})

test("keeps codes readable and offers manual copying when clipboard access fails", async () => {
  previewTemplateMock.mockRejectedValueOnce(new Error(
    "以下商品编码未匹配到商品信息档案：C2153112DF8080255。请联系商品部维护商品信息档案后再导入；本次未导入任何数据。"
  ))
  const { user, dialog, ui } = await openImport()
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"))
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  const alert = within(await ui.findByRole("alert"))
  const copy = alert.getByRole("button", { name: "复制编码" })
  await user.click(copy)
  expect(alert.getByRole("status")).toHaveTextContent("复制失败，请选中编码手动复制。")
  expect(alert.getByText("C2153112DF8080255")).toBeInTheDocument()
  expect(copy).toHaveFocus()
  expect(alert.queryByRole("button", { name: "已复制" })).not.toBeInTheDocument()
})

test("keeps purchase order import working with the shared upload", async () => {
  const { user, dialog, ui } = await openImport("purchase-orders")
  expect(ui.queryByRole("group", { name: "导入方式" })).not.toBeInTheDocument()
  expect(ui.getByRole("button", { name: "模版下载" })).toBeInTheDocument()
  expect(ui.queryByRole("combobox", { name: "导入品牌" })).not.toBeInTheDocument()
  const file = selectFile(dialog, "采购单.xlsx")
  await user.click(ui.getByRole("button", { name: "预检查" }))
  expect(purchaseTaskMock).toHaveBeenCalledWith(
    expect.objectContaining({ file, document_type: "进货订单", preview: true, brand: undefined })
  )
  expect(purchaseTaskMock).toHaveBeenCalledOnce()
  await user.click(await ui.findByRole("button", { name: "确认导入" }))
  expect(purchaseTaskMock).toHaveBeenLastCalledWith(
    expect.objectContaining({ file, document_type: "进货订单", preview: false, brand: undefined })
  )
  expect(importPurchaseMock).not.toHaveBeenCalled()
  expect(previewPurchaseMock).not.toHaveBeenCalled()
})

test.each(["inventory", "purchase-orders"] as const)("%s imports clear old search and pagination only after confirmed success", async (mode) => {
  const prefix = `hede:session-query:v1:anonymous:inventory:${mode}:`
  const previousFilters = { summary: "旧摘要", date_start: "2020-01-01", product_code: "OLD" }
  window.sessionStorage.setItem(prefix + "submittedFilters", JSON.stringify(previousFilters))
  window.sessionStorage.setItem(prefix + "searchSummary", JSON.stringify("旧摘要"))
  window.sessionStorage.setItem(prefix + "page", "3")
  window.sessionStorage.setItem(prefix + "sortRules", JSON.stringify([{ key: "date", direction: "asc" }]))
  let imported = false
  listInventoryMock.mockImplementation(async ({ page, summary }) => ({
    items: imported && page === 1 && !summary ? [{
      id: 88, document_number: "IMPORT-NEW", document_type: mode === "inventory" ? "进货单" : "进货订单",
      summary: "本次导入", total_count: "2", amount: "100", extra_fields: {},
    }] : [], total: imported ? 1 : 30,
  }))
  const { user, dialog, ui } = await openImport(mode)
  selectFile(dialog)
  await user.click(ui.getByRole("button", { name: "预检查" }))
  await ui.findByRole("button", { name: "确认导入" })
  expect(listInventoryMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, summary: "旧摘要" }))
  expect(JSON.parse(window.sessionStorage.getItem(prefix + "submittedFilters")!)).toEqual(previousFilters)
  imported = true
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  await screen.findByRole("alertdialog", { name: "导入完成" })
  await waitFor(() => expect(listInventoryMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, summary: undefined, product_code: undefined, sortRules: undefined })))
  expect(await screen.findByText("IMPORT-NEW")).toBeInTheDocument()
  expect(JSON.parse(window.sessionStorage.getItem(prefix + "searchSummary")!)).toBe("")
})

test("failed template imports retain the previous list filters and page", async () => {
  const prefix = "hede:session-query:v1:anonymous:inventory:inventory:"
  window.sessionStorage.setItem(prefix + "submittedFilters", JSON.stringify({ summary: "保留条件" }))
  window.sessionStorage.setItem(prefix + "page", "3")
  importTemplateMock.mockImplementationOnce(async (payload) => ({ ...importTask("failed", payload.taskId), error: "校验失败" }))
  const { ui } = await confirmTemplateImport()
  await ui.findByText(/校验失败/)
  expect(listInventoryMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, summary: "保留条件" }))
})

const purchaseConflictPreview: PurchaseImportPreview = {
  total: 4,
  conflicts: [
    { key: "first", date: "2026-10-01", summary: "采购甲", document_type: "进货订单", existing_number: "JHDD-001", can_merge: true },
    { key: "second", date: "2026-10-02", summary: "采购乙", document_type: "进货订单", existing_number: "JHDD-002", can_merge: true },
    { key: "third", date: "2026-10-03", summary: "采购丙", document_type: "进货订单", existing_number: "", can_merge: false },
  ],
}

async function openPurchaseConflictPreview() {
  purchaseTaskMock.mockImplementationOnce(async (payload) => ({
    ...importTask("succeeded", payload.taskId), result: null, preview: purchaseConflictPreview,
  }))
  const opened = await openImport("purchase-orders")
  const file = selectFile(opened.dialog, "重复采购单.xlsx")
  await opened.user.click(opened.ui.getByRole("button", { name: "预检查" }))
  await opened.ui.findByRole("region", { name: "采购单重复处理" })
  return { ...opened, file }
}

test("applies a batch decision only to selected purchase conflicts and submits all choices after confirmation", async () => {
  const { user, ui, file } = await openPurchaseConflictPreview()
  const rows = within(ui.getByRole("list", { name: "重复采购单" })).getAllByRole("listitem")
  expect(ui.getByRole("button", { name: "应用到已选" })).toBeDisabled()
  await user.selectOptions(within(rows[0]).getByRole("combobox"), "new")
  await user.type(ui.getByRole("textbox", { name: "第 1 张单据的新摘要" }), "采购甲补单")
  await user.click(ui.getByRole("checkbox", { name: "选择第 2 张重复单据" }))
  await user.click(ui.getByRole("checkbox", { name: "选择第 3 张重复单据" }))
  expect(ui.getByRole("checkbox", { name: "全选重复单据" })).toBePartiallyChecked()
  await user.selectOptions(ui.getByRole("combobox", { name: "批量处理方式" }), "skip")
  await user.click(ui.getByRole("button", { name: "应用到已选" }))
  expect(within(rows[0]).getByRole("combobox")).toHaveValue("new")
  expect(ui.getByRole("textbox", { name: "第 1 张单据的新摘要" })).toHaveValue("采购甲补单")
  expect(within(rows[1]).getByRole("combobox")).toHaveValue("skip")
  expect(within(rows[2]).getByRole("combobox")).toHaveValue("skip")
  expect(ui.getByText("待选择 0 张")).toBeInTheDocument()
  expect(purchaseTaskMock).toHaveBeenCalledOnce()
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(purchaseTaskMock).toHaveBeenLastCalledWith(expect.objectContaining({
    file, preview: false,
    decisions: {
      first: { action: "new", new_summary: "采购甲补单" },
      second: { action: "skip", new_summary: "" },
      third: { action: "skip", new_summary: "" },
    },
  }))
  expect(purchaseTaskMock).toHaveBeenCalledTimes(2)
})

test("bulk overwrite preserves ineligible conflicts and still allows individual adjustments", async () => {
  const { user, ui } = await openPurchaseConflictPreview()
  const rows = within(ui.getByRole("list", { name: "重复采购单" })).getAllByRole("listitem")
  await user.selectOptions(within(rows[2]).getByRole("combobox"), "skip")
  await user.click(ui.getByRole("checkbox", { name: "全选重复单据" }))
  await user.selectOptions(ui.getByRole("combobox", { name: "批量处理方式" }), "overwrite")
  await user.click(ui.getByRole("button", { name: "应用到已选" }))
  expect(within(rows[0]).getByRole("combobox")).toHaveValue("overwrite")
  expect(within(rows[1]).getByRole("combobox")).toHaveValue("overwrite")
  expect(within(rows[2]).getByRole("combobox")).toHaveValue("skip")
  expect(ui.getByText(/2 张单据设置“覆盖已有单据”。1 张不支持覆盖/)).toBeInTheDocument()
  await user.selectOptions(within(rows[0]).getByRole("combobox"), "skip")
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(purchaseTaskMock).toHaveBeenLastCalledWith(expect.objectContaining({
    preview: false, decisions: {
      first: { action: "skip", new_summary: "" },
      second: { action: "overwrite", new_summary: "" },
      third: { action: "skip", new_summary: "" },
    },
  }))
})

test("selects only pending conflicts, validates new summaries and clears only selected decisions", async () => {
  const { user, ui, dialog } = await openPurchaseConflictPreview()
  const rows = within(ui.getByRole("list", { name: "重复采购单" })).getAllByRole("listitem")
  await user.selectOptions(within(rows[0]).getByRole("combobox"), "skip")
  await user.click(ui.getByRole("button", { name: "仅选未处理" }))
  expect(ui.getByRole("checkbox", { name: "选择第 1 张重复单据" })).not.toBeChecked()
  expect(ui.getByRole("checkbox", { name: "选择第 2 张重复单据" })).toBeChecked()
  expect(ui.getByRole("checkbox", { name: "选择第 3 张重复单据" })).toBeChecked()
  await user.selectOptions(ui.getByRole("combobox", { name: "批量处理方式" }), "new")
  await user.click(ui.getByRole("button", { name: "应用到已选" }))
  expect(ui.getByText("待选择 0 张 · 待补摘要 2 张")).toBeInTheDocument()
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(ui.getByRole("alert")).toHaveTextContent("新建时必须填写不同的摘要")
  expect(purchaseTaskMock).toHaveBeenCalledOnce()
  await user.type(ui.getByRole("textbox", { name: "第 2 张单据的新摘要" }), "采购乙")
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(ui.getByRole("alert")).toHaveTextContent("新建时必须填写不同的摘要")
  await user.selectOptions(ui.getByRole("combobox", { name: "批量处理方式" }), "clear")
  await user.click(ui.getByRole("button", { name: "应用到已选" }))
  expect(ui.queryByRole("alert")).not.toBeInTheDocument()
  expect(within(rows[0]).getByRole("combobox")).toHaveValue("skip")
  expect(within(rows[1]).getByRole("combobox")).toHaveValue("")
  expect(within(rows[2]).getByRole("combobox")).toHaveValue("")
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(ui.getByRole("alert")).toHaveTextContent("选择覆盖、新增或取消该单据")
  selectFile(dialog, "另一批.xlsx")
  expect(ui.queryByRole("region", { name: "采购单重复处理" })).not.toBeInTheDocument()
  purchaseTaskMock.mockImplementationOnce(async (payload) => ({
    ...importTask("succeeded", payload.taskId), result: null, preview: purchaseConflictPreview,
  }))
  await user.click(ui.getByRole("button", { name: "预检查" }))
  await ui.findByRole("region", { name: "采购单重复处理" })
  expect(ui.getByRole("checkbox", { name: "全选重复单据" })).not.toBeChecked()
  expect(ui.getByRole("combobox", { name: "批量处理方式" })).toHaveValue("")
  expect(ui.getByText("待选择 3 张")).toBeInTheDocument()
})

test("locks bulk and individual purchase decisions while the confirmed import runs", async () => {
  const { user, ui } = await openPurchaseConflictPreview()
  await user.click(ui.getByRole("checkbox", { name: "全选重复单据" }))
  await user.selectOptions(ui.getByRole("combobox", { name: "批量处理方式" }), "new")
  await user.click(ui.getByRole("button", { name: "应用到已选" }))
  for (let index = 1; index <= 3; index++) {
    await user.type(ui.getByRole("textbox", { name: `第 ${index} 张单据的新摘要` }), `补单${index}`)
  }
  purchaseTaskMock.mockImplementationOnce(async (payload) => importTask("running", payload.taskId))
  getPurchaseTaskMock.mockResolvedValue(importTask("running"))
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  expect(await ui.findByRole("button", { name: "等待结果" })).toBeDisabled()
  const section = within(ui.getByRole("region", { name: "采购单重复处理" }))
  for (const control of [...section.getAllByRole("checkbox"), ...section.getAllByRole("combobox"), ...section.getAllByRole("textbox"), ...section.getAllByRole("button")]) {
    expect(control).toBeDisabled()
  }
  expect(purchaseTaskMock).toHaveBeenCalledTimes(2)
  expect(purchaseTaskMock).toHaveBeenLastCalledWith(expect.objectContaining({
    preview: false, decisions: {
      first: { action: "new", new_summary: "补单1" },
      second: { action: "new", new_summary: "补单2" },
      third: { action: "new", new_summary: "补单3" },
    },
  }))
})

test("keeps a purchase import running beyond two minutes and only queries after reconnecting", async () => {
  const { user, dialog, ui } = await openImport("purchase-orders")
  selectFile(dialog, "大采购单.xlsx")
  await user.click(ui.getByRole("button", { name: "预检查" }))
  await ui.findByRole("button", { name: "确认导入" })
  purchaseTaskMock.mockRejectedValueOnce(new TypeError("Failed to fetch"))
  getPurchaseTaskMock.mockResolvedValue(importTask("running"))
  await user.click(ui.getByRole("button", { name: "确认导入" }))
  await waitFor(() => expect(getPurchaseTaskMock).toHaveBeenCalledOnce())
  const taskId = purchaseTaskMock.mock.calls[1][0].taskId
  expect(window.sessionStorage.getItem("purchase-import-task:1")).toBe(taskId)
  vi.useFakeTimers()
  await act(async () => { await vi.advanceTimersByTimeAsync(123_000) })
  expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(purchaseTaskMock).toHaveBeenCalledTimes(2)
  getPurchaseTaskMock.mockResolvedValue(importTask("succeeded", taskId))
  await act(async () => {
    window.dispatchEvent(new Event("online"))
    await vi.advanceTimersByTimeAsync(1)
  })
  vi.useRealTimers()
  expect(await screen.findByRole("alertdialog", { name: "导入完成" })).toBeInTheDocument()
  expect(window.sessionStorage.getItem("purchase-import-task:1")).toBeNull()
  expect(purchaseTaskMock).toHaveBeenCalledTimes(2)
})

test("restores purchase batches independently from inventory batches after refreshing", async () => {
  const taskId = "c".repeat(32)
  window.sessionStorage.setItem("purchase-import-task:1", taskId)
  window.sessionStorage.setItem("inventory-import-task:1", "d".repeat(32))
  getPurchaseTaskMock.mockResolvedValue(importTask("running", taskId))
  render(<InventoryPage mode="purchase-orders" />)
  const dialog = await screen.findByRole("dialog", { name: "导入采购单" })
  await waitFor(() => expect(getPurchaseTaskMock).toHaveBeenCalledWith(taskId, expect.any(AbortSignal)))
  expect(within(dialog).getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(getTaskMock).not.toHaveBeenCalled()
  expect(purchaseTaskMock).not.toHaveBeenCalled()
  expect(window.sessionStorage.getItem("inventory-import-task:1")).toBe("d".repeat(32))
})

test.each(["purchase-orders", "inventory"] as const)("recovers a missing %s batch only after server confirmation, without uploading again", async (mode) => {
  const user = userEvent.setup()
  const taskId = "c".repeat(32)
  const key = (mode === "purchase-orders" ? "purchase-import-task:" : "inventory-import-task:") + "1"
  window.sessionStorage.setItem(key, taskId)
  getTaskMock.mockRejectedValue(new ApiError(404, "未找到该导入批次"))
  getPurchaseTaskMock.mockRejectedValue(new ApiError(404, "未找到该导入批次"))
  let resolve!: (result: { closed: boolean; task: InventoryImportTask }) => void
  resolveMissingTaskMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
  render(<InventoryPage mode={mode} />)
  const dialog = await screen.findByRole("dialog", { name: mode === "purchase-orders" ? "导入采购单" : "导入单据明细" })
  const ui = within(dialog)
  const recover = await ui.findByRole("button", { name: "核验并重新预检查" })
  await waitFor(() => expect(recover).toBeEnabled())
  await user.click(recover)
  expect(resolveMissingTaskMock).toHaveBeenCalledExactlyOnceWith(taskId, mode === "purchase-orders" ? "purchase" : "inventory", expect.any(AbortSignal))
  expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(recover).toBeDisabled()
  expect(window.sessionStorage.getItem(key)).toBe(taskId)
  await act(async () => resolve({ closed: true, task: { ...importTask("failed", taskId), result: null } }))
  expect(window.sessionStorage.getItem(key)).toBeNull()
  expect(ui.getByText(/服务器确认未接收此批次/)).toBeInTheDocument()
  expect(ui.queryByRole("button", { name: "等待结果" })).not.toBeInTheDocument()
  expect(ui.getByLabelText("Excel 文件")).toBeEnabled()
  expect(purchaseTaskMock).not.toHaveBeenCalled()
  expect(importTemplateMock).not.toHaveBeenCalled()
})

test("keeps a missing batch locked when recovery cannot contact the server", async () => {
  const user = userEvent.setup()
  const taskId = "c".repeat(32)
  window.sessionStorage.setItem("purchase-import-task:1", taskId)
  getPurchaseTaskMock.mockRejectedValue(new ApiError(404, "未找到该导入批次"))
  resolveMissingTaskMock.mockRejectedValueOnce(new TypeError("Offline"))
  render(<InventoryPage mode="purchase-orders" />)
  const dialog = await screen.findByRole("dialog", { name: "导入采购单" })
  const ui = within(dialog)
  const recover = await ui.findByRole("button", { name: "核验并重新预检查" })
  await waitFor(() => expect(recover).toBeEnabled())
  await user.click(recover)
  expect(await screen.findByRole("alertdialog", { name: "暂时无法恢复导入" })).toHaveTextContent("旧批次仍保留")
  await user.click(screen.getByRole("button", { name: "确定" }))
  expect(window.sessionStorage.getItem("purchase-import-task:1")).toBe(taskId)
  expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(purchaseTaskMock).not.toHaveBeenCalled()
})

test("continues checking when a delayed submission was received before recovery", async () => {
  const user = userEvent.setup()
  const taskId = "c".repeat(32)
  window.sessionStorage.setItem("purchase-import-task:1", taskId)
  getPurchaseTaskMock.mockRejectedValue(new ApiError(404, "未找到该导入批次"))
  resolveMissingTaskMock.mockResolvedValueOnce({ closed: false, task: importTask("running", taskId) })
  render(<InventoryPage mode="purchase-orders" />)
  const dialog = await screen.findByRole("dialog", { name: "导入采购单" })
  const ui = within(dialog)
  const recover = await ui.findByRole("button", { name: "核验并重新预检查" })
  await waitFor(() => expect(recover).toBeEnabled())
  await user.click(recover)
  expect(ui.getByRole("status")).toHaveTextContent("正在导入")
  expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(window.sessionStorage.getItem("purchase-import-task:1")).toBe(taskId)
  expect(purchaseTaskMock).not.toHaveBeenCalled()
})

test("opens the upload picker with the keyboard and keeps remove a separate button", async () => {
  const user = userEvent.setup()
  const onFileChange = vi.fn()
  render(
    <InventoryImportUpload
      file={new File(["excel"], "单据.xlsx")}
      onFileChange={onFileChange}
    />
  )
  const input = screen.getByLabelText("Excel 文件")
  const click = vi.spyOn(input, "click")
  screen.getByRole("button", { name: "更换 Excel 文件" }).focus()
  await user.keyboard("{Enter}")
  expect(click).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "移除已选文件" }))
  expect(onFileChange).toHaveBeenCalledWith(null)
  expect(click).toHaveBeenCalledOnce()
})

test("ignores drops while disabled", () => {
  const onFileChange = vi.fn()
  render(
    <InventoryImportUpload file={null} disabled onFileChange={onFileChange} />
  )
  const target = screen.getByRole("button", { name: "选择 Excel 文件" })
  fireEvent.drop(target, {
    dataTransfer: {
      files: [new File(["excel"], "单据.xlsx")],
      types: ["Files"],
    },
  })
  expect(onFileChange).not.toHaveBeenCalled()
  expect(target).toBeDisabled()
})

function importTask(
  status: InventoryImportTask["status"],
  taskId = "a".repeat(32)
): InventoryImportTask {
  return {
    task_id: taskId,
    filename: "进货单.xlsx",
    status,
    result:
      status === "succeeded"
        ? {
            created: 2,
            replaced: 0,
            skipped: 0,
            details: 2,
            message: "成功导入 2 张单据",
          }
        : null,
    error: status === "failed" ? "商品资料不完整，本批次未提交" : null,
    error_status: status === "failed" ? 400 : null,
  }
}

async function confirmTemplateImport() {
  const opened = await openImport()
  selectFile(opened.dialog)
  await opened.user.click(opened.ui.getByRole("button", { name: "预检查" }))
  await opened.user.click(
    await opened.ui.findByRole("button", { name: "确认导入" })
  )
  return opened
}

test("tracks a background batch, prevents duplicate submission and refreshes on success", async () => {
  let resolveStatus!: (task: InventoryImportTask) => void
  importTemplateMock.mockImplementationOnce(async (payload) =>
    importTask("queued", payload.taskId)
  )
  getTaskMock.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveStatus = resolve
      })
  )
  const { user, ui } = await confirmTemplateImport()
  await waitFor(() => expect(getTaskMock).toHaveBeenCalledOnce())
  expect(ui.getByRole("status")).toHaveTextContent("等待后台处理")
  expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(ui.getByRole("button", { name: "更换 Excel 文件" })).toBeDisabled()
  const taskId = importTemplateMock.mock.calls[0][0].taskId
  expect(window.sessionStorage.getItem("inventory-import-task:1")).toBe(taskId)
  const previousLoads = listInventoryMock.mock.calls.length
  await user.click(ui.getByRole("button", { name: "关闭" }))
  const banner = screen.getByRole("region", { name: "导入任务状态" })
  expect(within(banner).getByRole("status")).toHaveTextContent("文件已接收")
  await user.click(within(banner).getByRole("button", { name: "立即核验" }))
  expect(getTaskMock).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "查看导入进度" }))
  expect(importTemplateMock).toHaveBeenCalledOnce()
  await act(async () => resolveStatus(importTask("succeeded", taskId)))
  expect(
    await screen.findByRole("alertdialog", { name: "导入完成" })
  ).toHaveTextContent("成功导入 2 张单据")
  await waitFor(() =>
    expect(listInventoryMock.mock.calls.length).toBeGreaterThan(previousLoads)
  )
  expect(window.sessionStorage.getItem("inventory-import-task:1")).toBeNull()
})

test.each([
  new TypeError("Failed to fetch"),
  new ApiError(408, "Request Timeout"),
])(
  "verifies a lost submission response rather than declaring the import failed: %s",
  async (error) => {
    importTemplateMock.mockRejectedValueOnce(error)
    const { dialog } = await confirmTemplateImport()
    await waitFor(() => expect(getTaskMock).toHaveBeenCalledOnce())
    expect(
      await screen.findByRole("alertdialog", { name: "导入完成" })
    ).toHaveTextContent("成功导入 2 张单据")
    expect(dialog).not.toBeInTheDocument()
    expect(importTemplateMock).toHaveBeenCalledOnce()
    expect(window.sessionStorage.getItem("inventory-import-task:1")).toBeNull()
  }
)

test.each([500, 404])(
  "keeps an uncertain batch locked after a status HTTP %s",
  async (status) => {
    importTemplateMock.mockImplementationOnce(async (payload) =>
      importTask("running", payload.taskId)
    )
    getTaskMock.mockRejectedValueOnce(new ApiError(status, "查询暂不可用"))
    const { user, ui } = await confirmTemplateImport()
    await waitFor(() =>
      expect(ui.getByRole("status")).toHaveTextContent(
        status === 404 ? "暂未查到该批次" : "连接暂时中断"
      )
    )
    expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
    expect(window.sessionStorage.getItem("inventory-import-task:1")).toMatch(
      /^[a-f0-9]{32}$/
    )
    await user.click(ui.getByRole("button", { name: "关闭" }))
    expect(importTemplateMock).toHaveBeenCalledOnce()
    expect(
      screen.queryByRole("alertdialog", { name: "导入完成" })
    ).not.toBeInTheDocument()
  }
)

test("restores a saved batch after refreshing without resubmitting a file", async () => {
  const taskId = "b".repeat(32)
  window.sessionStorage.setItem("inventory-import-task:1", taskId)
  let resolveStatus!: (task: InventoryImportTask) => void
  getTaskMock.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveStatus = resolve
      })
  )
  render(<InventoryPage />)
  const dialog = await screen.findByRole("dialog", { name: "导入单据明细" })
  await waitFor(() =>
    expect(getTaskMock).toHaveBeenCalledWith(taskId, expect.any(AbortSignal))
  )
  expect(within(dialog).getByRole("status")).toHaveTextContent("恢复并核验")
  expect(importTemplateMock).not.toHaveBeenCalled()
  await act(async () => resolveStatus(importTask("succeeded", taskId)))
  expect(
    await screen.findByRole("alertdialog", { name: "导入完成" })
  ).toBeInTheDocument()
  expect(importTemplateMock).not.toHaveBeenCalled()
})

test("reports a persisted failure and requires another preview", async () => {
  importTemplateMock.mockImplementationOnce(async (payload) =>
    importTask("queued", payload.taskId)
  )
  getTaskMock.mockResolvedValueOnce(importTask("failed"))
  const { ui } = await confirmTemplateImport()
  expect(await ui.findByRole("alert")).toHaveTextContent("本批次未提交")
  expect(ui.getByRole("alert")).toHaveTextContent("重新预检查")
  expect(ui.getByRole("alert")).toHaveTextContent("不支持从中断位置继续")
  expect(ui.getByRole("button", { name: "预检查" })).toBeEnabled()
  expect(window.sessionStorage.getItem("inventory-import-task:1")).toBeNull()
  expect(
    screen.queryByRole("alertdialog", { name: "导入完成" })
  ).not.toBeInTheDocument()
})

test("does not report success or unlock resubmission if a success payload is incomplete", async () => {
  importTemplateMock.mockImplementationOnce(async (payload) =>
    importTask("queued", payload.taskId)
  )
  getTaskMock.mockResolvedValueOnce({
    ...importTask("succeeded"),
    result: null,
  })
  const { ui } = await confirmTemplateImport()
  await waitFor(() =>
    expect(ui.getByRole("status")).toHaveTextContent("核验导入结果")
  )
  expect(
    window.sessionStorage.getItem("inventory-import-task:1")
  ).not.toBeNull()
  expect(
    screen.queryByRole("alertdialog", { name: "导入完成" })
  ).not.toBeInTheDocument()
})

test("explains an outdated backend endpoint without silently falling back to synchronous import", async () => {
  importTemplateMock.mockRejectedValueOnce(new ApiError(404, "Not Found"))
  const { ui } = await confirmTemplateImport()
  expect(await ui.findByRole("alert")).toHaveTextContent("更新并重启后端")
  expect(ui.getByRole("button", { name: "确认导入" })).toBeEnabled()
  expect(getTaskMock).not.toHaveBeenCalled()
  expect(window.sessionStorage.getItem("inventory-import-task:1")).toBeNull()
})

test("recovers from a temporary status error, observes running and refreshes only after committed success", async () => {
  importTemplateMock.mockImplementationOnce(async (payload) =>
    importTask("queued", payload.taskId)
  )
  getTaskMock
    .mockRejectedValueOnce(new ApiError(500, "暂时离线"))
    .mockResolvedValueOnce(importTask("running"))
    .mockResolvedValueOnce(importTask("succeeded"))
  const { ui } = await confirmTemplateImport()
  await waitFor(() =>
    expect(ui.getByRole("status")).toHaveTextContent("连接暂时中断")
  )
  const initialLoads = listInventoryMock.mock.calls.length
  expect(
    window.sessionStorage.getItem("inventory-import-task:1")
  ).not.toBeNull()
  await waitFor(
    () => expect(ui.getByRole("status")).toHaveTextContent("后台正在导入"),
    { timeout: 5000 }
  )
  expect(listInventoryMock.mock.calls.length).toBe(initialLoads)
  expect(
    window.sessionStorage.getItem("inventory-import-task:1")
  ).not.toBeNull()
  expect(
    await screen.findByRole(
      "alertdialog",
      { name: "导入完成" },
      { timeout: 5000 }
    )
  ).toHaveTextContent("成功导入 2 张单据")
  await waitFor(() =>
    expect(listInventoryMock.mock.calls.length).toBeGreaterThan(initialLoads)
  )
  expect(importTemplateMock).toHaveBeenCalledOnce()
  expect(getTaskMock).toHaveBeenCalledTimes(3)
  expect(window.sessionStorage.getItem("inventory-import-task:1")).toBeNull()
}, 15_000)

test("keeps submission distinct from accepted background processing", async () => {
  let resolveSubmission!: (task: InventoryImportTask) => void
  importTemplateMock.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveSubmission = resolve
      })
  )
  const { ui } = await confirmTemplateImport()
  expect(ui.getByRole("status")).toHaveTextContent("正在提交文件")
  expect(ui.getByRole("status")).toHaveTextContent("文件尚未确认接收")
  expect(ui.getByRole("button", { name: "关闭" })).toBeDisabled()
  expect(ui.queryByRole("button", { name: "立即核验" })).not.toBeInTheDocument()
  expect(getTaskMock).not.toHaveBeenCalled()
  const taskId = importTemplateMock.mock.calls[0][0].taskId
  await act(async () => resolveSubmission(importTask("succeeded", taskId)))
  expect(
    await screen.findByRole("alertdialog", { name: "导入完成" })
  ).toBeInTheDocument()
})

test("manual verification only queries the existing batch and preserves unknown results", async () => {
  importTemplateMock.mockImplementationOnce(async (payload) =>
    importTask("running", payload.taskId)
  )
  getTaskMock.mockRejectedValueOnce(new ApiError(404, "未找到批次"))
  const { user, ui } = await confirmTemplateImport()
  await waitFor(() =>
    expect(ui.getByRole("status")).toHaveTextContent("批次待确认")
  )
  const taskId = importTemplateMock.mock.calls[0][0].taskId
  expect(ui.getByText(taskId)).toBeInTheDocument()
  expect(ui.getByText(/不支持文件断点续传/)).toBeInTheDocument()
  await user.click(ui.getByRole("button", { name: "关闭" }))
  const banner = within(screen.getByRole("region", { name: "导入任务状态" }))
  expect(banner.getByRole("status")).toHaveTextContent("暂未查到该批次")
  await user.click(banner.getByRole("button", { name: "查看详情" }))
  const reopened = within(screen.getByRole("dialog", { name: "导入单据明细" }))
  expect(reopened.getByRole("status")).toHaveTextContent("批次待确认")
  await user.click(reopened.getByRole("button", { name: "立即核验" }))
  expect(
    await screen.findByRole("alertdialog", { name: "导入完成" })
  ).toBeInTheDocument()
  expect(getTaskMock).toHaveBeenCalledTimes(2)
  expect(getTaskMock).toHaveBeenLastCalledWith(taskId, expect.any(AbortSignal))
  expect(importTemplateMock).toHaveBeenCalledOnce()
})

test("rechecks when the connection returns without overlapping requests and cleans up on leaving", async () => {
  const taskId = "c".repeat(32)
  window.sessionStorage.setItem("inventory-import-task:1", taskId)
  let resolveStatus!: (task: InventoryImportTask) => void
  getTaskMock
    .mockRejectedValueOnce(new TypeError("Offline"))
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveStatus = resolve
        })
    )
  const { unmount } = render(<InventoryPage />)
  const dialog = await screen.findByRole("dialog", { name: "导入单据明细" })
  const ui = within(dialog)
  await waitFor(() =>
    expect(ui.getByRole("status")).toHaveTextContent("连接暂时中断")
  )
  act(() => window.dispatchEvent(new Event("online")))
  await waitFor(() => expect(getTaskMock).toHaveBeenCalledTimes(2))
  expect(ui.getByRole("button", { name: "立即核验" })).toBeDisabled()
  act(() => window.dispatchEvent(new Event("online")))
  expect(getTaskMock).toHaveBeenCalledTimes(2)
  await act(async () => resolveStatus(importTask("running", taskId)))
  expect(ui.getByRole("status")).toHaveTextContent("正在导入")
  unmount()
  act(() => window.dispatchEvent(new Event("online")))
  expect(getTaskMock).toHaveBeenCalledTimes(2)
  expect(importTemplateMock).not.toHaveBeenCalled()
})

test("does not unlock an unconfirmed batch after a prolonged disconnection", async () => {
  importTemplateMock.mockImplementationOnce(async (payload) =>
    importTask("queued", payload.taskId)
  )
  getTaskMock.mockRejectedValue(new TypeError("Offline"))
  const { user, ui } = await confirmTemplateImport()
  await waitFor(() =>
    expect(ui.getByRole("status")).toHaveTextContent("连接暂时中断")
  )
  const later = Date.now() + 180_000
  vi.spyOn(Date, "now").mockReturnValue(later)
  const previousLoads = listInventoryMock.mock.calls.length
  await user.click(ui.getByRole("button", { name: "立即核验" }))
  await waitFor(() =>
    expect(listInventoryMock.mock.calls.length).toBeGreaterThan(previousLoads)
  )
  expect(ui.getByRole("button", { name: "等待结果" })).toBeDisabled()
  expect(ui.getByRole("button", { name: "更换 Excel 文件" })).toBeDisabled()
  expect(ui.getByRole("status")).toHaveTextContent("不代表导入失败")
  expect(
    window.sessionStorage.getItem("inventory-import-task:1")
  ).not.toBeNull()
  expect(importTemplateMock).toHaveBeenCalledOnce()
})
