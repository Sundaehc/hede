import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { DEFAULT_PURCHASE_PRINT_TEMPLATE, PurchasePrintTemplateEditor } from "@/components/inventory-admin/purchase-print-template-editor"
import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import type { InventoryPrintLabel, InventoryRecord } from "@/lib/api"

const { labelsMock, currentTemplateMock } = vi.hoisted(() => ({
  labelsMock: vi.fn(), currentTemplateMock: vi.fn(),
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventoryPrintLabels: labelsMock,
  getPurchasePrintTemplate: currentTemplateMock,
  listPurchasePrintTemplates: async () => ({ items: [template] }),
  listDetails: async () => ({ items: [], total: 0 }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
  listSizeGroupOptions: async () => ({ items: [] }),
}))

const template = { template_key: "label", template_name: "测试模板", is_default: true, config: DEFAULT_PURCHASE_PRINT_TEMPLATE }
const first: InventoryPrintLabel = {
  detail_id: 51, product_code: "ACTUAL-01", size_name: "35", size_barcode: "EU35",
  barcode: "ACTUAL-01BLACKEU35", copies: 10000, brand: "cbanner_womens", brand_name: "C°BANNER",
  product_level: "合格品", color_name: "黑色", upper_material: "羊皮革", product_name: "当前单据女鞋",
  execution_standard: "ACTUAL-STD", origin: "中国",
}
const second: InventoryPrintLabel = { ...first, size_name: "36", size_barcode: "EU36", barcode: "ACTUAL-01BLACKEU36", copies: 2 }
const third: InventoryPrintLabel = { ...first, detail_id: 52, product_code: "ACTUAL-02", color_name: "白色", barcode: "ACTUAL-02WHITEEU35" }

function props() {
  return {
    open: true, documentId: 42, documentNumber: "JHDD-CURRENT", config: DEFAULT_PURCHASE_PRINT_TEMPLATE,
    templates: [template], selectedTemplateKey: "label", templateName: "测试模板",
    onOpenChange: vi.fn(), onTemplateChange: vi.fn(), onCreateTemplate: vi.fn(),
    onDuplicateTemplate: vi.fn(), onSetDefaultTemplate: vi.fn(), onDeleteTemplate: vi.fn(), onSave: vi.fn(),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
  labelsMock.mockResolvedValue({ items: [first, second, third], label_count: 20002 })
  currentTemplateMock.mockResolvedValue({ config: DEFAULT_PURCHASE_PRINT_TEMPLATE, template })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test("renders actual print data and barcodes, and switches product and size without expanding copies", async () => {
  const user = userEvent.setup()
  render(<PurchasePrintTemplateEditor {...props()} />)
  const preview = await screen.findByRole("region", { name: "当前单据标签预览" })
  expect(labelsMock).toHaveBeenCalledExactlyOnceWith(42, expect.any(AbortSignal))
  expect(screen.getByText("当前单据：JHDD-CURRENT")).toBeInTheDocument()
  for (const value of ["货号：ACTUAL-01", "尺码：35", "帮面材质：羊皮革", "品名：当前单据女鞋", "执行标准：ACTUAL-STD", first.barcode]) {
    expect(within(preview).getByText(value)).toBeInTheDocument()
  }
  expect(screen.queryByText(/RH663189DP5/)).not.toBeInTheDocument()
  const select = screen.getByRole("combobox", { name: "预览商品和尺码" })
  expect(within(select).getAllByRole("option")).toHaveLength(3)
  expect(screen.getByText(/此尺码打印 10000 张/)).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "上一个标签" })).toBeDisabled()
  await user.click(screen.getByRole("button", { name: "下一个标签" }))
  expect(within(preview).getByText("尺码：36")).toBeInTheDocument()
  expect(within(preview).getByLabelText(`条码 ${second.barcode}`)).toBeInTheDocument()
  await user.selectOptions(select, "2")
  expect(within(preview).getByText("货号：ACTUAL-02")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "下一个标签" })).toBeDisabled()
  await user.click(screen.getByRole("button", { name: "上一个标签" }))
  expect(within(preview).getByText("尺码：36")).toBeInTheDocument()
  const barcode = within(preview).getByRole("img", { name: `条码 ${second.barcode}` })
  expect(barcode).toHaveAttribute("viewBox", "0 0 576 81")
  const bars = Array.from(barcode.querySelectorAll("g rect"))
  expect(bars.length).toBeGreaterThan(0)
  expect(Number(bars[0].getAttribute("x"))).toBeGreaterThanOrEqual(20)
  for (const bar of bars) expect(Number(bar.getAttribute("width")) % 2).toBe(0)
})

test("updates the current label immediately as the template changes and preserves the draft while switching labels", async () => {
  const user = userEvent.setup()
  const callbacks = props()
  render(<PurchasePrintTemplateEditor {...callbacks} />)
  const preview = await screen.findByRole("region", { name: "当前单据标签预览" })
  fireEvent.change(screen.getByLabelText("字段标题"), { target: { value: "款号" } })
  expect(within(preview).getByText("款号：ACTUAL-01")).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("横坐标 (mm)"), { target: { value: "4" } })
  expect(within(preview).getByText("款号：ACTUAL-01").closest(".purchase-print-element")).toHaveStyle({ left: "5%" })
  await user.selectOptions(screen.getByRole("combobox", { name: "预览商品和尺码" }), "2")
  expect(within(preview).getByText("款号：ACTUAL-02")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "保存模板" }))
  expect(callbacks.onSave).toHaveBeenCalledWith(expect.objectContaining({
    elements: expect.arrayContaining([expect.objectContaining({ id: "product-code", label: "款号", x: 4 })]),
  }), "测试模板")
  expect(labelsMock).toHaveBeenCalledTimes(1)
})

test("shows empty and failure states without fabricated data, retries and refreshes latest labels", async () => {
  const user = userEvent.setup()
  labelsMock.mockRejectedValueOnce(new Error("SKU 未维护尺码数量"))
  render(<PurchasePrintTemplateEditor {...props()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("SKU 未维护尺码数量")
  expect(screen.queryByRole("region", { name: "当前单据标签预览" })).not.toBeInTheDocument()
  labelsMock.mockResolvedValueOnce({ items: [], label_count: 0 })
  await user.click(screen.getByRole("button", { name: "重新加载预览" }))
  await screen.findByText(/当前采购单没有数量大于 0 的尺码明细/)
  expect(screen.getByRole("combobox", { name: "预览商品和尺码" })).toBeDisabled()
  labelsMock.mockResolvedValueOnce({ items: [{ ...first, product_name: "最新品名" }], label_count: 10000 })
  await user.click(screen.getByRole("button", { name: "刷新标签预览" }))
  await screen.findByText("品名：最新品名")
})

test("cancels late requests when the current document changes or the editor closes", async () => {
  let resolveOld!: (result: { items: InventoryPrintLabel[]; label_count: number }) => void
  labelsMock.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
  const callbacks = props()
  const view = render(<PurchasePrintTemplateEditor {...callbacks} />)
  expect(screen.getByText("正在加载当前单据标签…")).toBeInTheDocument()
  const oldSignal = labelsMock.mock.calls[0][1] as AbortSignal
  labelsMock.mockResolvedValueOnce({ items: [third], label_count: 1 })
  view.rerender(<PurchasePrintTemplateEditor {...callbacks} documentId={43} documentNumber="NEXT-DOCUMENT" />)
  await screen.findByText("货号：ACTUAL-02")
  expect(oldSignal.aborted).toBe(true)
  await act(async () => { resolveOld({ items: [first], label_count: 1 }) })
  expect(screen.queryByText("货号：ACTUAL-01")).not.toBeInTheDocument()
  const currentSignal = labelsMock.mock.lastCall![1] as AbortSignal
  view.rerender(<PurchasePrintTemplateEditor {...callbacks} documentId={43} open={false} />)
  expect(currentSignal.aborted).toBe(true)
  view.rerender(<PurchasePrintTemplateEditor {...callbacks} documentId={43} />)
  await screen.findByText("货号：ACTUAL-01")
  expect(labelsMock).toHaveBeenCalledTimes(3)
})

test("opens preview for the detail panel's current purchase document", async () => {
  const user = userEvent.setup()
  render(<InventoryDetailPanel record={{ id: 77, document_type: "进货订单", document_number: "JHDD-77" } as InventoryRecord}
    suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />)
  await user.click(screen.getByRole("button", { name: "自定义打印模板" }))
  await screen.findByRole("region", { name: "当前单据标签预览" })
  expect(labelsMock).toHaveBeenCalledExactlyOnceWith(77, expect.any(AbortSignal))
  expect(screen.getByText("当前单据：JHDD-77")).toBeInTheDocument()
})
