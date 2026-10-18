import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { ProductTable } from "@/components/product-admin/product-table"

afterEach(cleanup)

function renderProductTable(page: number) {
  const onPageChange = vi.fn()
  render(
    <ProductTable
      items={[]}
      total={87000}
      page={page}
      pageSize={20}
      pageSizes={[20, 50]}
      isLoading={false}
      error={null}
      selectedKeys={new Set()}
      onToggleSelect={vi.fn()}
      onToggleSelectAll={vi.fn()}
      onPageChange={onPageChange}
      onPageSizeChange={vi.fn()}
    />
  )
  return onPageChange
}

test("renders distinct long page numbers and lets the jump control wrap below navigation", () => {
  renderProductTable(4350)

  const navigation = screen.getByRole("navigation")
  const previousPage = within(navigation).getByText("4349")
  const currentPage = within(navigation).getByText("4350")
  expect(previousPage).toHaveClass("min-w-8", "px-2.5")
  expect(currentPage).toHaveAttribute("aria-current", "page")
  expect(currentPage).not.toHaveClass("size-8")
  expect(navigation).toHaveClass("w-auto", "max-w-full")
  expect(navigation.parentElement).toHaveClass("flex-wrap", "justify-center")
  expect(
    screen.getByRole("spinbutton", { name: "跳转页码" }).parentElement
  ).toHaveClass("shrink-0")
  expect(screen.getByLabelText("Go to next page")).toHaveClass(
    "pointer-events-none"
  )
})

test("preserves adjacent-page navigation and validated page jumps", async () => {
  const user = userEvent.setup()
  const onPageChange = renderProductTable(2100)

  await user.click(screen.getByText("2101"))
  expect(onPageChange).toHaveBeenLastCalledWith(2101)
  await user.click(screen.getByLabelText("Go to previous page"))
  expect(onPageChange).toHaveBeenLastCalledWith(2099)
  await user.click(screen.getByLabelText("Go to next page"))
  expect(onPageChange).toHaveBeenLastCalledWith(2101)

  const jumpInput = screen.getByRole("spinbutton", { name: "跳转页码" })
  await user.type(jumpInput, "4350{Enter}")
  expect(onPageChange).toHaveBeenLastCalledWith(4350)
  onPageChange.mockClear()
  await user.clear(jumpInput)
  await user.type(jumpInput, "4351{Enter}")
  expect(onPageChange).not.toHaveBeenCalled()
})
