import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { InventoryDetailPanel } from "@/components/inventory-admin/inventory-detail-panel"
import { PageTabs } from "@/components/auth/page-tabs"
import { ApiError, type InventoryDetail, type InventoryRecord } from "@/lib/api"
import { SessionQueryProvider } from "@/lib/session-query-state"

const { mockListDetails, mockUpdateDetail, mockCreateDetail } = vi.hoisted(() => ({
  mockListDetails: vi.fn(),
  mockUpdateDetail: vi.fn(),
  mockCreateDetail: vi.fn(),
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listDetails: mockListDetails,
  updateDetail: mockUpdateDetail,
  createDetail: mockCreateDetail,
  getPinnedPageTabs: vi.fn().mockResolvedValue({ pinned_paths: [] }),
  listInventoryAccountSubjects: vi.fn().mockResolvedValue({
    items: [{ id: 16, name: "大底收入", category: "收入类" }],
  }),
  listSizeGroupOptions: vi.fn().mockResolvedValue({
    items: [
      { id: 1, name: "女鞋尺码组220-250", product_count: 0, items: ["220", "225", "230", "235", "240", "245", "250"].map((size, index) => ({ id: index, size_name: size, barcode: size, sort_order: index })) },
      { id: 2, name: "男鞋尺码组240-270", product_count: 0, items: ["240", "245", "250", "255", "260", "265", "270"].map((size, index) => ({ id: index + 10, size_name: size, barcode: size, sort_order: index })) },
    ],
  }),
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/inventory",
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({
    user: { id: 1, role_code: "super_admin", department_code: "开发部" },
    hasPermission: () => true,
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

test("keeps the detail header and controls above page tabs while edit dialogs remain above the drawer", async () => {
  const user = userEvent.setup()
  const onClose = vi.fn()
  const view = render(
    <SessionQueryProvider userId={1}>
      <PageTabs />
      <InventoryDetailPanel record={record} suppliers={[]} onClose={onClose} onTotalChanged={vi.fn()} />
    </SessionQueryProvider>
  )
  await screen.findByText("大底费用")
  const tabHeader = screen.getByRole("navigation", { name: "页面标签" }).closest("header")!
  const overlay = view.container.querySelector(".fixed.inset-0")!
  const panel = screen.getByRole("heading", { name: /单据明细/ }).closest(".fixed")!
  expect(tabHeader).toHaveClass("z-[70]")
  expect(overlay).toHaveClass("z-[80]")
  expect(panel).toHaveClass("z-[90]", "inset-y-0")
  expect(within(panel as HTMLElement).getByRole("button", { name: "新增明细" })).toBeVisible()
  expect(within(panel as HTMLElement).getByRole("button", { name: "关闭单据明细" })).toBeVisible()

  await user.click(screen.getByRole("button", { name: "编辑明细" }))
  const dialog = screen.getByRole("dialog", { name: "编辑明细" })
  expect(dialog.closest('[data-slot="dialog-portal"]')).toHaveClass("z-[120]")
  await user.click(within(dialog).getByRole("button", { name: "取消" }))
  await user.click(screen.getByRole("button", { name: "关闭单据明细" }))
  expect(onClose).toHaveBeenCalledOnce()
})

async function editAccountingSubject(documentType = "应付款减少") {
  const user = userEvent.setup()
  render(<InventoryDetailPanel record={{ ...record, document_type: documentType }} suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />)
  await screen.findByText("大底费用")
  await user.click(screen.getByRole("button", { name: "编辑明细" }))
  const dialog = screen.getByRole("dialog", { name: "编辑明细" })
  await user.click(within(dialog).getByLabelText("费用项目名 / 科目"))
  await user.click(within(dialog).getByRole("option", { name: "大底收入" }))
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  return dialog
}

test("creates an accounting detail with a searched subject and preserves the entered amount", async () => {
  const user = userEvent.setup()
  const onTotalChanged = vi.fn()
  mockCreateDetail.mockResolvedValue({ item: { ...detail, product_name: "大底收入" } })
  render(<InventoryDetailPanel record={record} suppliers={[]} onClose={vi.fn()} onTotalChanged={onTotalChanged} />)
  await screen.findByText("大底费用")
  await user.click(screen.getByRole("button", { name: "新增明细" }))
  const dialog = screen.getByRole("dialog", { name: "新增明细" })
  await user.type(within(dialog).getByLabelText("减少金额"), "681.25")
  await user.type(within(dialog).getByLabelText("备注"), "测试费用")
  await user.click(within(dialog).getByLabelText("费用项目名 / 科目"))
  await user.type(within(dialog).getByRole("combobox", { name: "搜索科目" }), "大底")
  await user.click(within(dialog).getByRole("option", { name: "大底收入" }))
  expect(within(dialog).getByLabelText("减少金额")).toHaveValue(681.25)
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() => expect(mockCreateDetail).toHaveBeenCalledWith(6787, {
    product_code: "",
    product_name: "大底收入",
    amount: "681.25",
    remark: "测试费用",
  }))
  await waitFor(() => expect(onTotalChanged).toHaveBeenCalledOnce())
  expect(screen.queryByRole("dialog", { name: "新增明细" })).not.toBeInTheDocument()
})

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

test("preserves size quantities when reselecting a group and updates size columns only after changing selection", async () => {
  const user = userEvent.setup()
  mockUpdateDetail.mockResolvedValueOnce({ item: detail, message: "明细更新成功" })
  mockListDetails.mockResolvedValue({ items: [{
    ...detail,
    product_code: "TEST-001",
    product_name: "测试商品",
    quantity: "1",
    unit_price: "149",
    amount: 149,
    size_quantities: { "235": "1" },
    extra_fields: { size_range: "女鞋尺码组220-250", size_labels: "220|225|230|235|240|245|250" },
  }], total: 1, page: 1, page_size: 100 })
  render(<InventoryDetailPanel record={{ ...record, document_type: "进货单" }} suppliers={[]} onClose={vi.fn()} onTotalChanged={vi.fn()} />)
  await screen.findByText("测试商品")
  await user.click(screen.getByRole("button", { name: "编辑明细" }))
  const dialog = screen.getByRole("dialog", { name: "编辑明细" })
  await user.click(within(dialog).getByLabelText("尺码段"))
  await user.click(await within(dialog).findByRole("option", { name: "女鞋尺码组220-250 7 码" }))
  expect(within(dialog).getByLabelText("数量")).toHaveValue(1)
  expect(within(dialog).getByLabelText("金额")).toHaveValue(149)
  expect(within(dialog).getByLabelText("235")).toHaveValue("1")
  await user.click(within(dialog).getByLabelText("尺码段"))
  await user.type(within(dialog).getByRole("combobox", { name: "搜索尺码段" }), "男鞋")
  await user.click(within(dialog).getByRole("option", { name: "男鞋尺码组240-270 7 码" }))
  expect(within(dialog).queryByLabelText("235")).not.toBeInTheDocument()
  expect(within(dialog).getByLabelText("270")).toHaveValue("")
  expect(within(dialog).getByLabelText("数量")).toHaveValue(null)
  expect(within(dialog).getByLabelText("单价")).toHaveValue(149)
  await user.type(within(dialog).getByLabelText("270"), "2")
  expect(within(dialog).getByLabelText("数量")).toHaveValue(2)
  expect(within(dialog).getByLabelText("金额")).toHaveValue(298)
  await user.click(within(dialog).getByRole("button", { name: "保存" }))
  await waitFor(() => expect(mockUpdateDetail).toHaveBeenCalledWith(6787, 130839, expect.objectContaining({
    quantity: "2",
    unit_price: "149",
    amount: "298.00",
    size_quantities: { "270": "2" },
    extra_fields: expect.objectContaining({ size_range: "男鞋尺码组240-270", size_labels: "240|245|250|255|260|265|270" }),
  })))
})
