import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"
import { PostedProductChangeDialog } from "@/components/product-admin/posted-product-change-dialog"
import type { PostedProductChangeWarning } from "@/lib/posted-product-change"

afterEach(cleanup)

test("shows every affected document across pages and prevents closing while saving", async () => {
  const user = userEvent.setup()
  const warning: PostedProductChangeWarning = { code: "posted_product_change_confirmation", message: "已过账",
    confirmation_token: "a".repeat(64), document_count: 21, detail_count: 21,
    changes: [{ field: "size_range", label: "尺码段", before: "35-40", after: "35-41" }],
    documents: Array.from({ length: 21 }, (_, index) => ({ id: index + 1, document_number: `POSTED-${index + 1}`,
      document_type: "进货单", date: "2026-11-13", detail_count: 1 })) }
  const onCancel = vi.fn()
  const props = { warning, onCancel, onConfirm: vi.fn(), saving: false, error: null }
  const view = render(<PostedProductChangeDialog {...props} />)
  expect(screen.getByText("POSTED-1")).toBeInTheDocument()
  expect(screen.queryByText("POSTED-21")).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "下一页单据" }))
  await user.click(screen.getByRole("button", { name: "下一页单据" }))
  expect(screen.getByText("POSTED-21")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "下一页单据" })).toBeDisabled()
  view.rerender(<PostedProductChangeDialog {...props} saving />)
  expect(screen.getByRole("button", { name: "返回修改" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "保存中…" })).toBeDisabled()
  await user.keyboard("{Escape}")
  expect(onCancel).not.toHaveBeenCalled()
})
