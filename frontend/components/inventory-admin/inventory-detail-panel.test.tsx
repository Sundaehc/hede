import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import { ApiError, type InventoryDetail, type InventoryRecord } from "@/lib/api"

const { mockListDetails, mockUpdateDetail } = vi.hoisted(() => ({
  mockListDetails: vi.fn(),
  mockUpdateDetail: vi.fn(),
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listDetails: mockListDetails,
  updateDetail: mockUpdateDetail,
  listInventoryAccountSubjects: vi.fn().mockResolvedValue({
    items: [{ id: 16, name: "大底收入", category: "收入类" }],
  }),
}))

const detail = {
  id: 130839,
  document_id: 6787,
  product_identity_id: null,
  product_code: null,
  product_name: "大底费用",
  color_spec: null,
  color_barcode: null,
  color_name: null,
  size_quantities: null,
  extra_fields: null,
  quantity: null,
  unit_price: null,
  amount: 2787.8,
  remark: null,
  created_at: null,
  updated_at: null,
} satisfies InventoryDetail

const record = {
  id: 6787,
  document_number: "YFKJS-2026-04-30-0001",
  document_type: "应付款减少",
  summary: "大底费用",
} as InventoryRecord

beforeEach(() => {
  vi.clearAllMocks()
  mockListDetails.mockResolvedValue({ items: [detail], total: 1, page: 1, page_size: 100 })
})

afterEach(cleanup)

async function editAccountingSubject(documentType = "应付款减少") {
  const user = userEvent.setup()
  render(<InventoryDetailPanel record={{ ...record, document_type: documentType }} suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />)
  await screen.findByText("大底费用")
  await user.click(screen.getByRole("button", { name: "编辑明细" }))
  const dialog = screen.getByRole("dialog", { name: "编辑明细" })
  await user.selectOptions(within(dialog).getByLabelText("费用项目名 / 科目"), "大底收入")
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  return dialog
}

test.each(["应付款减少", "应付款增加", "应收款减少", "应收款增加"])("saves a changed subject for %s with a numeric amount", async (documentType) => {
  mockUpdateDetail.mockResolvedValue({ item: { ...detail, product_name: "大底收入" }, message: "明细更新成功" })

  await editAccountingSubject(documentType)

  await waitFor(() => expect(mockUpdateDetail).toHaveBeenCalledWith(6787, 130839, {
    product_code: "",
    product_name: "大底收入",
    amount: "2787.8",
    remark: "",
  }))
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "编辑明细" })).not.toBeInTheDocument())
})

test("shows a failed save inside the still-open edit dialog", async () => {
  mockUpdateDetail.mockRejectedValue(new ApiError(403, "没有编辑权限"))

  const dialog = await editAccountingSubject()

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("保存失败：没有编辑权限")
  expect(dialog).toBeInTheDocument()
})
