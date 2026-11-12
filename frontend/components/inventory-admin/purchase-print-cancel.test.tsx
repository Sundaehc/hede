import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import { DEFAULT_PURCHASE_PRINT_TEMPLATE } from "@/components/inventory-admin/purchase-print-template-editor"
import type { InventoryPrintLabel, InventoryRecord } from "@/lib/api"

const { labelsMock, printMock, cancelMock } = vi.hoisted(() => ({
  labelsMock: vi.fn(), printMock: vi.fn(), cancelMock: vi.fn(),
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listInventoryPrintLabels: labelsMock,
  getPurchasePrintTemplate: async () => ({ config: DEFAULT_PURCHASE_PRINT_TEMPLATE, template: null }),
  listDetails: async () => ({ items: [], total: 0 }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
  listSizeGroupOptions: async () => ({ items: [] }),
}))
vi.mock("@/lib/local-label-print", () => ({
  printLabelsWithLocalAgent: printMock, cancelLabelsWithLocalAgent: cancelMock,
}))

const record = { id: 42, document_type: "进货订单", document_number: "JHDD-42" } as InventoryRecord
const label = { product_code: "TEST-01", barcode: "TEST-0135", copies: 1 } as InventoryPrintLabel
const result = { ok: true, printed: 1, printer: "Test Printer" }

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function panel(nextRecord = record) {
  return <InventoryDetailPanel record={nextRecord} suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />
}

async function startPrint() {
  const user = userEvent.setup()
  await waitFor(() => expect(screen.getByRole("button", { name: "打印" })).toBeEnabled())
  await user.click(screen.getByRole("button", { name: "打印" }))
  return user
}

beforeEach(() => {
  vi.resetAllMocks()
  labelsMock.mockResolvedValue({ items: [label], label_count: 1 })
  cancelMock.mockResolvedValue({ ok: true, status: "cancelled" })
})
afterEach(cleanup)

test("cancels while loading labels and ignores their late arrival", async () => {
  const labels = deferred<{ items: InventoryPrintLabel[]; label_count: number }>()
  labelsMock.mockReturnValue(labels.promise)
  render(panel())
  const user = await startPrint()
  const signal = labelsMock.mock.calls[0][1] as AbortSignal
  await user.click(screen.getByRole("button", { name: "取消打印" }))
  expect(signal.aborted).toBe(true)
  expect(await screen.findByText("打印已取消")).toBeInTheDocument()
  await act(async () => labels.resolve({ items: [label], label_count: 1 }))
  expect(printMock).not.toHaveBeenCalled()
  expect(cancelMock).not.toHaveBeenCalled()
})

test("cancels bitmap preparation without contacting the agent", async () => {
  const print = deferred<typeof result>()
  printMock.mockReturnValue(print.promise)
  render(panel())
  const user = await startPrint()
  await waitFor(() => expect(printMock).toHaveBeenCalledOnce())
  await user.click(screen.getByRole("button", { name: "取消打印" }))
  expect(printMock.mock.calls[0][2].signal.aborted).toBe(true)
  await act(async () => print.resolve(result))
  expect(screen.queryByText("打印任务已发送")).not.toBeInTheDocument()
  expect(cancelMock).not.toHaveBeenCalled()
})

test("cancels a submitted request exactly once and ignores late success", async () => {
  const print = deferred<typeof result>()
  const cancel = deferred<{ ok: boolean; status: string }>()
  printMock.mockImplementation((_labels, _config, options) => {
    options.onSending()
    return print.promise
  })
  cancelMock.mockReturnValue(cancel.promise)
  render(panel())
  const user = await startPrint()
  await screen.findByText("正在发送...")
  await user.click(screen.getByRole("button", { name: "取消打印" }))
  expect(screen.getByRole("button", { name: "取消中..." })).toBeDisabled()
  expect(cancelMock).toHaveBeenCalledExactlyOnceWith(printMock.mock.calls[0][2].requestId)
  await act(async () => print.resolve(result))
  expect(screen.queryByText("打印任务已发送")).not.toBeInTheDocument()
  await act(async () => cancel.resolve({ ok: true, status: "cancelled" }))
  expect(await screen.findByText("已取消本次打印任务")).toBeInTheDocument()
})

test("keeps cancel available after sending and reports a task that already left the queue", async () => {
  printMock.mockImplementation(async (_labels, _config, options) => {
    options.onSending()
    return result
  })
  cancelMock.mockResolvedValue({ ok: true, status: "not_in_queue" })
  render(panel())
  const user = await startPrint()
  await screen.findByText("打印任务已发送")
  await user.click(screen.getByRole("button", { name: "确定" }))
  await user.click(screen.getByRole("button", { name: "取消打印" }))
  expect(await screen.findByText("任务已离开打印队列")).toBeInTheDocument()
})

test("keeps a failed cancellation available for retry", async () => {
  printMock.mockImplementation(async (_labels, _config, options) => {
    options.onSending()
    return result
  })
  cancelMock.mockRejectedValueOnce(new Error("请更新打印服务"))
  render(panel())
  const user = await startPrint()
  await screen.findByText("打印任务已发送")
  await user.click(screen.getByRole("button", { name: "确定" }))
  await user.click(screen.getByRole("button", { name: "取消打印" }))
  expect(await screen.findByText("取消打印未确认")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "确定" }))
  await user.click(screen.getByRole("button", { name: "取消打印" }))
  expect(await screen.findByText("已取消本次打印任务")).toBeInTheDocument()
  expect(cancelMock).toHaveBeenCalledTimes(2)
})

test("switching documents prevents an old preparation from printing or changing the new controls", async () => {
  const labels = deferred<{ items: InventoryPrintLabel[]; label_count: number }>()
  labelsMock.mockReturnValue(labels.promise)
  const view = render(panel())
  await startPrint()
  view.rerender(panel({ ...record, id: 43 }))
  await act(async () => labels.resolve({ items: [label], label_count: 1 }))
  expect(printMock).not.toHaveBeenCalled()
  expect(screen.queryByRole("button", { name: "取消打印" })).not.toBeInTheDocument()
  view.rerender(panel())
  await waitFor(() => expect(screen.getByRole("button", { name: "打印" })).toBeEnabled())
  expect(screen.queryByRole("button", { name: "取消打印" })).not.toBeInTheDocument()
})
