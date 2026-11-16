import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { PurchaseOrderDocumentPage } from "./purchase-order-document-page"
import { ApiError, type InventoryRecord } from "@/lib/api"
import { SessionQueryProvider } from "@/lib/session-query-state"

const { getRecord, listSuppliers, push, auth } = vi.hoisted(() => ({
  getRecord: vi.fn(),
  listSuppliers: vi.fn(),
  push: vi.fn(),
  auth: { allowed: true },
}))
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ hasPermission: () => auth.allowed }),
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  getInventoryRecord: getRecord,
  listSuppliers,
}))
vi.mock("./inventory-detail-panel", () => ({
  InventoryDetailPanel: ({
    record,
    presentation,
    onClose,
    onTotalChanged,
  }: {
    record: InventoryRecord
    presentation: string
    onClose: () => void
    onTotalChanged: () => void
  }) => (
    <section aria-label="采购单内容" data-presentation={presentation}>
      <p>{record.document_number}</p>
      <p>合计 {record.total_count}</p>
      <button onClick={onClose}>关闭单据明细</button>
      <button onClick={onTotalChanged}>保存明细</button>
    </section>
  ),
}))

function record(id = 42, total = "5") {
  return {
    id,
    document_number: `PO-${id}`,
    document_type: "进货订单",
    total_count: total,
  } as InventoryRecord
}
function fixture(id = "42") {
  return (
    <SessionQueryProvider userId={1}>
      <PurchaseOrderDocumentPage recordId={id} />
    </SessionQueryProvider>
  )
}
function savedTabs() {
  return JSON.parse(
    window.sessionStorage.getItem(
      "hede:session-query:v1:1:workspace:purchase-detail-tabs:v1"
    ) || "[]"
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  auth.allowed = true
  getRecord.mockResolvedValue(record())
  listSuppliers.mockResolvedValue({ items: [] })
})
afterEach(cleanup)

test("loads a document directly by ID in page mode and registers its title", async () => {
  render(fixture())
  expect(await screen.findByText("PO-42")).toBeInTheDocument()
  expect(getRecord).toHaveBeenCalledWith(42, expect.any(AbortSignal))
  expect(screen.getByRole("region", { name: "采购单内容" })).toHaveAttribute(
    "data-presentation",
    "page"
  )
  expect(savedTabs()).toEqual([{ id: 42, documentNumber: "PO-42" }])
})

test("refreshes document totals after a detail write and returns to the list while retaining the document tab", async () => {
  const user = userEvent.setup()
  render(fixture())
  await screen.findByText("合计 5")
  getRecord.mockResolvedValue(record(42, "8"))
  await user.click(screen.getByText("保存明细"))
  expect(await screen.findByText("合计 8")).toBeInTheDocument()
  expect(savedTabs()).toHaveLength(1)
  await user.click(screen.getByText("关闭单据明细"))
  expect(push).toHaveBeenCalledWith("/purchase-orders", { scroll: false })
  expect(savedTabs()).toEqual([{ id: 42, documentNumber: "PO-42" }])
  expect(
    JSON.parse(
      window.sessionStorage.getItem(
        "hede:session-query:v1:1:workspace:manual-tabs"
      ) || "[]"
    )
  ).toContain("/purchase-orders/42")
})

test("ignores late responses from a previous document and aborts its request", async () => {
  let resolve!: (value: InventoryRecord) => void
  getRecord.mockReturnValueOnce(
    new Promise<InventoryRecord>((done) => {
      resolve = done
    })
  )
  const view = render(fixture())
  const signal = getRecord.mock.calls[0][1] as AbortSignal
  getRecord.mockResolvedValue(record(43))
  view.rerender(fixture("43"))
  expect(await screen.findByText("PO-43")).toBeInTheDocument()
  expect(signal.aborted).toBe(true)
  await act(async () => resolve(record()))
  expect(screen.queryByText("PO-42")).not.toBeInTheDocument()
  expect(savedTabs()).toEqual([{ id: 43, documentNumber: "PO-43" }])
})

test("shows a deleted document error and supports retry without rendering stale data", async () => {
  getRecord.mockRejectedValueOnce(new ApiError(404, "Record not found"))
  render(fixture())
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "采购单不存在或已移入回收站"
  )
  expect(
    screen.queryByRole("region", { name: "采购单内容" })
  ).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole("button", { name: "重试" }))
  expect(await screen.findByText("PO-42")).toBeInTheDocument()
})

test("rejects a non-purchase document without rendering editing or printing controls", async () => {
  getRecord.mockResolvedValue({ ...record(), document_type: "进货单" })
  render(fixture())
  expect(await screen.findByRole("alert")).toHaveTextContent("该单据不是采购单")
  expect(
    screen.queryByRole("region", { name: "采购单内容" })
  ).not.toBeInTheDocument()
})

test.each(["0", "-1", "bad", "1.5", "9007199254740992"])(
  "does not fetch invalid document ID %s",
  async (id) => {
    render(fixture(id))
    expect(screen.getByRole("alert")).toHaveTextContent("采购单地址无效")
    expect(getRecord).not.toHaveBeenCalled()
  }
)

test("does not request document data without purchase permission", async () => {
  auth.allowed = false
  render(fixture())
  expect(screen.getByRole("alert")).toHaveTextContent("暂无采购单查看权限")
  await waitFor(() => expect(getRecord).not.toHaveBeenCalled())
  expect(listSuppliers).not.toHaveBeenCalled()
})
