import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { RecycleBinPagination } from "@/components/recycle-bin-page-jump"

afterEach(() => cleanup())

test("groups recycle page navigation with an accessible current-page status", async () => {
  const onPageChange = vi.fn()
  const user = userEvent.setup()
  render(<RecycleBinPagination page={2} totalPages={323} onPageChange={onPageChange} />)

  expect(screen.getByRole("navigation", { name: "回收站分页" })).toBeInTheDocument()
  const status = screen.getByRole("status", { name: "回收站当前页码" })
  expect(status).toHaveTextContent("2 / 323")
  expect(status).toHaveAttribute("aria-live", "polite")
  await user.click(screen.getByRole("button", { name: "上一页" }))
  expect(onPageChange).toHaveBeenLastCalledWith(1)
  await user.click(screen.getByRole("button", { name: "下一页" }))
  expect(onPageChange).toHaveBeenLastCalledWith(3)
})

test.each([
  [1, "上一页"],
  [323, "下一页"],
] as const)("keeps page %s boundary navigation disabled", (page, name) => {
  render(<RecycleBinPagination page={page} totalPages={323} onPageChange={vi.fn()} />)
  expect(screen.getByRole("button", { name })).toBeDisabled()
})

test("marks out-of-range jump pages invalid and restores a valid keyboard jump", async () => {
  const onPageChange = vi.fn()
  const user = userEvent.setup()
  render(<RecycleBinPagination page={1} totalPages={2} onPageChange={onPageChange} />)
  const input = screen.getByRole("spinbutton", { name: "回收站跳转页码" })
  await user.clear(input)
  await user.type(input, "3")
  expect(input).toHaveAttribute("aria-invalid", "true")
  expect(screen.getByRole("button", { name: "跳转" })).toBeDisabled()
  expect(onPageChange).not.toHaveBeenCalled()
  await user.clear(input)
  await user.type(input, "2{Enter}")
  expect(input).toHaveAttribute("aria-invalid", "false")
  expect(onPageChange).toHaveBeenCalledExactlyOnceWith(2)
})

test("updates jump input and status when the current page changes", async () => {
  const onPageChange = vi.fn()
  const user = userEvent.setup()
  const view = render(<RecycleBinPagination page={1} totalPages={323} onPageChange={onPageChange} />)
  const input = screen.getByRole("spinbutton", { name: "回收站跳转页码" })
  await user.clear(input)
  await user.type(input, "24")
  view.rerender(<RecycleBinPagination page={25} totalPages={323} onPageChange={onPageChange} />)
  expect(input).toHaveValue(25)
  expect(screen.getByRole("status", { name: "回收站当前页码" })).toHaveTextContent("25 / 323")
})

test("disables every pagination control while keeping the current page visible", () => {
  render(<RecycleBinPagination page={24} totalPages={323} disabled onPageChange={vi.fn()} />)
  for (const name of ["上一页", "下一页", "跳转"]) {
    expect(screen.getByRole("button", { name })).toBeDisabled()
  }
  expect(screen.getByRole("spinbutton", { name: "回收站跳转页码" })).toBeDisabled()
  expect(screen.getByRole("status", { name: "回收站当前页码" })).toHaveTextContent("24 / 323")
})
