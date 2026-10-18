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
} from "@/lib/api"

const {
  listInventoryMock,
  previewTemplateMock,
  importTemplateMock,
  getTaskMock,
  previewPurchaseMock,
  importPurchaseMock,
} = vi.hoisted(() => ({
  listInventoryMock: vi.fn(),
  previewTemplateMock: vi.fn(),
  importTemplateMock: vi.fn(),
  getTaskMock: vi.fn(),
  previewPurchaseMock: vi.fn(),
  importPurchaseMock: vi.fn(),
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

test("keeps purchase order import working with the shared upload", async () => {
  const { user, dialog, ui } = await openImport("purchase-orders")
  expect(ui.queryByRole("group", { name: "导入方式" })).not.toBeInTheDocument()
  expect(ui.getByRole("button", { name: "模版下载" })).toBeInTheDocument()
  const file = selectFile(dialog, "采购单.xlsx")
  await user.click(ui.getByRole("button", { name: "预检查" }))
  expect(previewPurchaseMock).toHaveBeenCalledWith(
    expect.objectContaining({ file, document_type: "进货订单" })
  )
  await waitFor(() =>
    expect(importPurchaseMock).toHaveBeenCalledWith(
      expect.objectContaining({ file, document_type: "进货订单" })
    )
  )
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
