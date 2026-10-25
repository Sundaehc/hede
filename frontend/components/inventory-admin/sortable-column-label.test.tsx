import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { SortableColumnLabel } from "@/components/inventory-admin/sortable-column-label"

afterEach(cleanup)

test("shows a compact neutral indicator and Chinese instructions before sorting", () => {
  render(<SortableColumnLabel label="日期" onClick={vi.fn()} />)

  const button = screen.getByRole("button", {
    name: "日期：未排序；点击按此列降序",
  })
  expect(button).toHaveAttribute("aria-pressed", "false")
  expect(button).toHaveAttribute(
    "title",
    "日期：未排序；点击按此列降序；按住上档键点击可追加或切换多列排序"
  )
  expect(button.querySelectorAll("svg")).toHaveLength(2)
  expect(button).toHaveTextContent(/^日期$/)
  expect(screen.queryByText("1")).not.toBeInTheDocument()
})

test.each([
  ["asc", "升序", "点击取消排序", "up", "down"],
  ["desc", "降序", "点击切换升序", "down", "up"],
] as const)(
  "highlights only the %s direction without a single-column priority badge",
  (direction, label, action, activeIcon, inactiveIcon) => {
    render(
      <SortableColumnLabel
        label="金额"
        sortRule={{ direction, index: 1, total: 1 }}
        onClick={vi.fn()}
      />
    )

    const button = screen.getByRole("button", {
      name: `金额：当前${label}；${action}`,
    })
    expect(button).toHaveAttribute("aria-pressed", "true")
    expect(button).toHaveClass("border-primary/15", "bg-primary/8")
    expect(button.querySelector(`.lucide-chevron-${activeIcon}`)).toHaveClass(
      "text-primary"
    )
    expect(button.querySelector(`.lucide-chevron-${inactiveIcon}`)).toHaveClass(
      "text-muted-foreground/25"
    )
    expect(screen.queryByText("1")).not.toBeInTheDocument()
  }
)

test("shows the priority badge only for multiple sorting columns", () => {
  const { rerender } = render(
    <SortableColumnLabel
      label="金额"
      sortRule={{ direction: "asc", index: 2, total: 2 }}
      onClick={vi.fn()}
    />
  )

  const button = screen.getByRole("button", {
    name: "金额：当前升序，第 2 优先级；点击按此列降序",
  })
  expect(screen.getByText("2")).toHaveAttribute("aria-hidden", "true")
  expect(button).toHaveAttribute(
    "title",
    expect.stringContaining("第 2 优先级")
  )

  rerender(
    <SortableColumnLabel
      label="金额"
      sortRule={{ direction: "asc", index: 1, total: 1 }}
      onClick={vi.fn()}
    />
  )
  expect(screen.queryByText("2")).not.toBeInTheDocument()
  expect(screen.queryByText("1")).not.toBeInTheDocument()
})

test("keeps keyboard activation and forwards the multiple-sort modifier", async () => {
  const user = userEvent.setup()
  const events: boolean[] = []
  render(
    <SortableColumnLabel
      label="日期"
      onClick={(event) => events.push(event.shiftKey)}
    />
  )

  await user.tab()
  expect(screen.getByRole("button")).toHaveFocus()
  await user.keyboard("{Enter}")
  await user.keyboard(" ")
  await user.keyboard("{Shift>}")
  await user.click(screen.getByRole("button"))
  await user.keyboard("{/Shift}")

  expect(events).toEqual([false, false, true])
})
