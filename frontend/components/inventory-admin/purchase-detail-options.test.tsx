import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryDetailPanel } from "./inventory-detail-panel"
import { DEFAULT_PURCHASE_PRINT_TEMPLATE } from "./purchase-print-template-editor"
import type {
  InventoryDetail,
  InventoryPrintLabel,
  InventoryRecord,
} from "@/lib/api"
import {
  clearSessionQueryStates,
  SessionQueryProvider,
} from "@/lib/session-query-state"

const { labelsMock, printMock, detailsMock } = vi.hoisted(() => ({
  labelsMock: vi.fn(),
  printMock: vi.fn(),
  detailsMock: vi.fn(),
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listDetails: detailsMock,
  listInventoryPrintLabels: labelsMock,
  getPurchasePrintTemplate: async () => ({
    config: DEFAULT_PURCHASE_PRINT_TEMPLATE,
    template: null,
  }),
  listInventoryAccountSubjects: async () => ({ items: [] }),
  listSizeGroupOptions: async () => ({ items: [] }),
}))
vi.mock("@/lib/local-label-print", () => ({
  printLabelsWithLocalAgent: printMock,
  cancelLabelsWithLocalAgent: vi.fn(),
}))

const record = {
  id: 42,
  document_type: "进货订单",
  document_number: "JHDD-42",
  total_count: "5",
  amount: "50",
} as InventoryRecord
const detailDefaults = {
  product_identity_id: null,
  product_name: null,
  color_spec: null,
  color_barcode: null,
  color_name: null,
  extra_fields: null,
  unit_price: null,
  created_at: null,
  updated_at: null,
}
const details = [
  {
    ...detailDefaults,
    id: 101,
    document_id: 42,
    product_code: "SAME",
    remark: "第一行",
    quantity: "2",
    amount: 20,
    size_quantities: { "35": "2" },
  },
  {
    ...detailDefaults,
    id: 102,
    document_id: 42,
    product_code: "SAME",
    remark: "第二行",
    quantity: "3",
    amount: 30,
    size_quantities: { "36": "3" },
  },
] satisfies InventoryDetail[]
const labels = [
  { detail_id: 101, product_code: "SAME", barcode: "SAME35", copies: 2 },
  { detail_id: 102, product_code: "SAME", barcode: "SAME36", copies: 3 },
] as InventoryPrintLabel[]

function panel(userId = 1, nextRecord = record) {
  return (
    <SessionQueryProvider userId={userId}>
      <InventoryDetailPanel
        record={nextRecord}
        suppliers={[]}
        onClose={vi.fn()}
        onTotalChanged={vi.fn()}
      />
    </SessionQueryProvider>
  )
}
async function loaded() {
  await screen.findByText("第二行")
}
function columnNames() {
  return within(screen.getByRole("table"))
    .getAllByRole("columnheader")
    .map((cell) => cell.textContent)
}
async function settings() {
  await userEvent.click(screen.getByRole("button", { name: "字段位置" }))
  return screen.getByRole("dialog", { name: "明细字段位置" })
}

beforeEach(() => {
  window.localStorage.clear()
  clearSessionQueryStates()
  vi.clearAllMocks()
  detailsMock.mockResolvedValue({
    items: details,
    total: 2,
    page: 1,
    page_size: 100,
  })
  labelsMock.mockResolvedValue({ items: labels, label_count: 5 })
  printMock.mockResolvedValue({ ok: true, printed: 5, printer: "Test" })
})
afterEach(cleanup)

test("purchase remarks display the archive value read-only, including long remarks", async () => {
  const remark = "外箱注明商品货号，鞋垫增加防磨条，左右脚分别包装并附上说明。"
  detailsMock.mockResolvedValue({ items: [{ ...details[0], remark }], total: 1, page: 1, page_size: 100 })
  render(panel())
  await screen.findByText(remark)
  await userEvent.click(screen.getByRole("button", { name: "编辑明细" }))
  const input = screen.getByRole("textbox", { name: "商品备注" })
  expect(input).toHaveValue(remark)
  expect(input).toHaveAttribute("readonly")
  expect(screen.getByText("来自商品信息档案，请在商品档案中修改。")).toBeInTheDocument()
})

test("page presentation keeps the top tabs visible and returns through the detail close button", async () => {
  const onClose = vi.fn()
  const view = render(
    <SessionQueryProvider userId={1}>
      <nav aria-label="页面标签">采购单管理</nav>
      <InventoryDetailPanel
        record={record}
        suppliers={[]}
        presentation="page"
        onClose={onClose}
        onTotalChanged={vi.fn()}
      />
    </SessionQueryProvider>
  )
  await loaded()
  expect(view.container.querySelector(".fixed.inset-0")).toBeNull()
  const heading = screen.getByRole("heading", { name: /单据明细/ })
  expect(heading.closest(".fixed")).toBeNull()
  expect(screen.getByRole("navigation", { name: "页面标签" })).toBeVisible()
  expect(screen.getByRole("button", { name: "打印已选" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "字段位置" })).toBeVisible()
  await userEvent.click(screen.getByRole("button", { name: "关闭单据明细" }))
  expect(onClose).toHaveBeenCalledOnce()
})

test("prints only selected detail IDs even when goods codes match and an older server returns all labels", async () => {
  render(panel())
  await loaded()
  expect(screen.getByRole("button", { name: "打印已选" })).toBeDisabled()
  await userEvent.click(
    screen.getAllByRole("checkbox", { name: "选择明细 SAME" })[1]
  )
  await userEvent.click(screen.getByRole("button", { name: "打印已选（1）" }))
  await waitFor(() => expect(printMock).toHaveBeenCalledOnce())
  expect(labelsMock).toHaveBeenCalledExactlyOnceWith(
    42,
    expect.any(AbortSignal),
    [102]
  )
  expect(printMock.mock.calls[0][0]).toHaveLength(3)
  expect(
    printMock.mock.calls[0][0].every(
      (label: InventoryPrintLabel) =>
        label.detail_id === 102 && label.barcode === "SAME36"
    )
  ).toBe(true)
})

test("whole-order printing still prints every detail after selecting only one row", async () => {
  render(panel())
  await loaded()
  await userEvent.click(
    screen.getAllByRole("checkbox", { name: "选择明细 SAME" })[0]
  )
  await userEvent.click(screen.getByRole("button", { name: "打印" }))
  await waitFor(() => expect(printMock).toHaveBeenCalledOnce())
  expect(labelsMock).toHaveBeenCalledExactlyOnceWith(
    42,
    expect.any(AbortSignal)
  )
  expect(printMock.mock.calls[0][0]).toHaveLength(5)
})

test("does not send a print job for selected rows without printable sizes", async () => {
  labelsMock.mockResolvedValue({ items: [], label_count: 0 })
  render(panel())
  await loaded()
  await userEvent.click(screen.getByRole("checkbox", { name: "选择全部明细" }))
  await userEvent.click(screen.getByRole("button", { name: "打印已选（2）" }))
  expect(
    await screen.findByText(
      "勾选明细没有数量大于 0 的尺码标签，请核对数量和尺码。"
    )
  ).toBeInTheDocument()
  expect(printMock).not.toHaveBeenCalled()
})

test("moves headers, rows and totals together, remembers the order across orders, and isolates accounts", async () => {
  const view = render(panel())
  await loaded()
  const dialog = await settings()
  const source = dialog.querySelector('[data-column-key="amount"]')!
  const target = dialog.querySelector('[data-column-key="product_code"]')!
  fireEvent.dragStart(source, {
    dataTransfer: { setData: vi.fn(), effectAllowed: "" },
  })
  fireEvent.dragOver(target)
  fireEvent.drop(target)
  await userEvent.click(
    within(dialog).getByRole("button", { name: "应用顺序" })
  )
  expect(columnNames().slice(1, 3)).toEqual(["金额", "商品货号"])
  const table = screen.getByRole("table") as HTMLTableElement
  expect(table.tBodies[0].rows[0].cells[1]).toHaveTextContent("20")
  expect(table.tFoot!.rows[0].cells[1]).toHaveTextContent("50")
  expect(table.tBodies[0].rows[0].cells[1]).toHaveClass("sticky", "left-10")
  view.unmount()
  // Browser reload clears temporary queries before mounting the page again.
  clearSessionQueryStates()
  window.sessionStorage.clear()
  const another = render(panel(1, { ...record, id: 43 }))
  await loaded()
  expect(columnNames()[1]).toBe("金额")
  another.unmount()
  render(panel(2))
  await loaded()
  expect(columnNames()[1]).toBe("商品货号")
})

test("cancels field changes, applies keyboard moves, and restores the default order", async () => {
  render(panel())
  await loaded()
  const dialog = await settings()
  await userEvent.click(
    within(dialog).getByRole("button", { name: "上移商品备注" })
  )
  await userEvent.click(within(dialog).getByRole("button", { name: "取消" }))
  expect(columnNames()[1]).toBe("商品货号")
  const reopened = await settings()
  await userEvent.click(
    within(reopened).getByRole("button", { name: "上移商品备注" })
  )
  await userEvent.click(
    within(reopened).getByRole("button", { name: "应用顺序" })
  )
  expect(columnNames()[1]).toBe("商品备注")
  const reset = await settings()
  await userEvent.click(within(reset).getByRole("button", { name: "恢复默认" }))
  await userEvent.click(within(reset).getByRole("button", { name: "应用顺序" }))
  expect(columnNames()[1]).toBe("商品货号")
})

test("moves size columns as one group without changing their internal order", async () => {
  render(panel())
  await loaded()
  const dialog = await settings()
  const source = dialog.querySelector('[data-column-key="sizes"]')!
  const target = dialog.querySelector('[data-column-key="product_code"]')!
  fireEvent.dragStart(source, {
    dataTransfer: { setData: vi.fn(), effectAllowed: "" },
  })
  fireEvent.drop(target)
  await userEvent.click(
    within(dialog).getByRole("button", { name: "应用顺序" })
  )
  expect(columnNames().slice(1, 4)).toEqual(["35", "36", "商品货号"])
  const table = screen.getByRole("table") as HTMLTableElement
  expect(table.tBodies[0].rows[0].cells[1]).toHaveTextContent("2")
  expect(table.tBodies[0].rows[1].cells[2]).toHaveTextContent("3")
})
