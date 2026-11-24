import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import type { SupplierChangeRequest } from "@/lib/api"
import { SupplierChangeReviewDialog } from "./supplier-change-review-dialog"

const { list, review } = vi.hoisted(() => ({ list: vi.fn(), review: vi.fn() }))
vi.mock("@/lib/api", () => ({
  listSupplierChanges: list,
  reviewSupplierChange: review,
}))
const item: SupplierChangeRequest = {
  id: 9,
  supplier_id: 4,
  supplier_name: "鞋密码（千百度女鞋）",
  supplier_brand: "womens",
  supplier_factory_code: "Q95",
  status: "pending",
  changes: [
    { field: "brand", label: "品牌", before: "womens", after: "hejin" },
  ],
  expense_document_count: 3,
  requester_id: 10,
  requester_name: "财务同事",
  reviewer_name: null,
  review_note: null,
  created_at: "2026-11-24T01:00:00Z",
  reviewed_at: null,
}
const brands = [
  { id: 1, code: "womens", name: "千百度女鞋" },
  { id: 2, code: "hejin", name: "千百度赫锦" },
]

beforeEach(() => {
  vi.resetAllMocks()
  list.mockResolvedValue({
    items: [item],
    total: 1,
    page_size: 20,
    can_review: true,
  })
})
afterEach(cleanup)

test("shows the proposed brand and requires a separate confirmation before applying it", async () => {
  const user = userEvent.setup()
  const onApproved = vi.fn()
  list.mockResolvedValueOnce({
    items: [item],
    total: 1,
    page_size: 20,
    can_review: true,
  })
  list.mockResolvedValue({
    items: [],
    total: 0,
    page_size: 20,
    can_review: true,
  })
  review.mockResolvedValue({
    review: { ...item, status: "approved" },
    message: "供应商已更新",
  })
  render(
    <SupplierChangeReviewDialog
      userId={20}
      brands={brands}
      onClose={vi.fn()}
      onApproved={onApproved}
    />
  )
  const table = await screen.findByRole("table", { name: "申请 #9 的修改内容" })
  expect(within(table).getByText("千百度女鞋")).toBeInTheDocument()
  expect(within(table).getByText("千百度赫锦")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "审核通过" }))
  expect(review).not.toHaveBeenCalled()
  await user.click(screen.getByRole("button", { name: "确认通过" }))
  expect(await screen.findByText("#9 · 供应商已更新")).toBeInTheDocument()
  expect(review).toHaveBeenCalledExactlyOnceWith(9, "approve", "")
  expect(onApproved).toHaveBeenCalledOnce()
})

test("shows an applicant their own pending request without offering a decision", async () => {
  render(
    <SupplierChangeReviewDialog
      userId={10}
      brands={brands}
      onClose={vi.fn()}
      onApproved={vi.fn()}
    />
  )
  expect(await screen.findByText(item.supplier_name)).toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "审核通过" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "驳回申请" })
  ).not.toBeInTheDocument()
})
