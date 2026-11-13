import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import { DEFAULT_PURCHASE_PRINT_TEMPLATE } from "@/components/inventory-admin/purchase-print-template-editor"
import type { InventoryPrintLabel, InventoryRecord } from "@/lib/api"

const { labelsMock, printMock } = vi.hoisted(() => ({ labelsMock: vi.fn(), printMock: vi.fn() }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventoryPrintLabels: labelsMock,
  getPurchasePrintTemplate: async () => ({ config, template }),
  listPurchasePrintTemplates: async () => ({ items: [template] }),
  listDetails: async () => ({ items: [], total: 0 }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
  listSizeGroupOptions: async () => ({ items: [] }),
}))
vi.mock("@/lib/local-label-print", () => ({
  printLabelsWithLocalAgent: printMock,
  cancelLabelsWithLocalAgent: vi.fn(),
}))

const config = {
  ...DEFAULT_PURCHASE_PRINT_TEMPLATE,
  elements: [{ ...DEFAULT_PURCHASE_PRINT_TEMPLATE.elements[0], id: "production-date", field: "production_date" as const, label: "生产日期" }],
}
const template = { template_key: "dated-label", template_name: "生产日期标签", is_default: true, config }
const record = { id: 42, document_type: "进货订单", document_number: "JHDD-42" } as InventoryRecord
const label = { detail_id: 1, product_code: "TEST-01", barcode: "TEST-0135", size_name: "35", copies: 2 } as InventoryPrintLabel
function panel(nextRecord = record) {
  return <InventoryDetailPanel record={nextRecord} suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date(2026, 10, 13, 0, 15))
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} })
  labelsMock.mockResolvedValue({ items: [label, { ...label, detail_id: 2, size_name: "36", copies: 1 }], label_count: 3 })
  printMock.mockResolvedValue({ ok: true, printed: 3, printer: "Test Printer" })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

test("defaults to the local current date and prints the same date on every label", async () => {
  const user = userEvent.setup()
  render(panel())
  expect(screen.queryByLabelText("生产日期")).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole("button", { name: "打印" })).toBeEnabled())
  await user.click(screen.getByRole("button", { name: "打印" }))
  await waitFor(() => expect(printMock).toHaveBeenCalledOnce())
  const printed = printMock.mock.calls[0][0] as InventoryPrintLabel[]
  expect(printed).toHaveLength(3)
  expect(printed.every((item) => item.production_date === "2026-11-13")).toBe(true)
})

test("shares the chosen production date between the editor preview and actual printing", async () => {
  const user = userEvent.setup()
  render(panel())
  await user.click(screen.getByRole("button", { name: "自定义打印模板" }))
  const preview = await screen.findByRole("region", { name: "当前单据标签预览" })
  expect(within(preview).getByText("生产日期：2026-11-13")).toBeInTheDocument()
  const editor = screen.getByRole("dialog")
  await user.click(within(editor).getByLabelText("生产日期"))
  await user.click(screen.getByRole("button", { name: "2026年11月6日" }))
  expect(within(preview).getByText("生产日期：2026-11-06")).toBeInTheDocument()
  await user.click(within(editor).getByRole("button", { name: "取消" }))
  expect(screen.queryByLabelText("生产日期")).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "打印" }))
  await waitFor(() => expect(printMock).toHaveBeenCalledOnce())
  expect((printMock.mock.calls[0][0] as InventoryPrintLabel[]).every((item) => item.production_date === "2026-11-06")).toBe(true)
})

test("resets a chosen date on document changes and uses today's date again when cleared", async () => {
  const user = userEvent.setup()
  const view = render(panel())
  await user.click(screen.getByRole("button", { name: "自定义打印模板" }))
  await screen.findByRole("region", { name: "当前单据标签预览" })
  expect(screen.getByLabelText("生产日期")).toHaveValue("2026-11-13")
  fireEvent.change(screen.getByLabelText("生产日期"), { target: { value: "2026-11-06" } })
  expect(screen.getByLabelText("生产日期")).toHaveValue("2026-11-06")
  fireEvent.change(screen.getByLabelText("生产日期"), { target: { value: "" } })
  expect(screen.getByLabelText("生产日期")).toHaveValue("2026-11-13")
  fireEvent.change(screen.getByLabelText("生产日期"), { target: { value: "2026-11-06" } })
  view.rerender(panel({ ...record, id: 43 }))
  await user.click(screen.getByRole("button", { name: "自定义打印模板" }))
  await screen.findByRole("region", { name: "当前单据标签预览" })
  expect(screen.getByLabelText("生产日期")).toHaveValue("2026-11-13")
  view.rerender(panel())
  await user.click(screen.getByRole("button", { name: "自定义打印模板" }))
  await screen.findByRole("region", { name: "当前单据标签预览" })
  expect(screen.getByLabelText("生产日期")).toHaveValue("2026-11-13")
})

test("captures the date when printing starts even if label loading crosses midnight", async () => {
  let resolveLabels!: (value: { items: InventoryPrintLabel[]; label_count: number }) => void
  labelsMock.mockReturnValueOnce(new Promise((resolve) => { resolveLabels = resolve }))
  const user = userEvent.setup()
  render(panel())
  await waitFor(() => expect(screen.getByRole("button", { name: "打印" })).toBeEnabled())
  await user.click(screen.getByRole("button", { name: "打印" }))
  expect(screen.queryByLabelText("生产日期")).not.toBeInTheDocument()
  vi.setSystemTime(new Date(2026, 10, 14, 0, 15))
  await act(async () => resolveLabels({ items: [label], label_count: 2 }))
  await waitFor(() => expect(printMock).toHaveBeenCalledOnce())
  expect((printMock.mock.calls[0][0] as InventoryPrintLabel[]).every((item) => item.production_date === "2026-11-13")).toBe(true)
})
