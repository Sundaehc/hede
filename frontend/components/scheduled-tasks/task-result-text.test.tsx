import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test } from "vitest"

import { TaskResultText } from "@/components/scheduled-tasks/task-result-text"

afterEach(cleanup)

test("shows short results without extra disclosure controls", () => {
  render(<TaskResultText value="导入完成：63798 条" />)
  expect(screen.getByText("导入完成：63798 条")).toHaveClass("line-clamp-2")
  expect(screen.queryByText("查看详情")).not.toBeInTheDocument()
})

test("limits huge error previews while preserving full diagnostics in a bounded disclosure", async () => {
  const user = userEvent.setup()
  const value = `IntegrityError: 唯一键冲突\n[parameters: ${"商品数据".repeat(3000)}]`
  const { container } = render(<TaskResultText value={value} />)
  const preview = container.querySelector("p")!
  expect(preview.textContent!.length).toBeLessThanOrEqual(221)
  expect(preview.textContent).toMatch(/^IntegrityError: 唯一键冲突/)
  expect(preview).toHaveClass("line-clamp-2", "break-all")
  const disclosure = container.querySelector("details")!
  const detailsText = container.querySelector("pre")!
  expect(disclosure).not.toHaveAttribute("open")
  expect(detailsText.textContent).toBe(value)
  expect(detailsText).toHaveClass(
    "max-h-60",
    "overflow-auto",
    "whitespace-pre-wrap"
  )
  await user.click(screen.getByText("查看详情"))
  expect(disclosure).toHaveAttribute("open")
  await user.click(screen.getByText("收起详情"))
  expect(disclosure).not.toHaveAttribute("open")
})

test("provides full details for short multiline failures", () => {
  const value = "IntegrityError: 唯一键冲突\nDETAIL: 货号已存在"
  const { container } = render(
    <TaskResultText value={value} className="text-red-600" />
  )
  expect(container.querySelector("p")).toHaveTextContent(
    "IntegrityError: 唯一键冲突 DETAIL: 货号已存在"
  )
  expect(screen.getByText("查看详情")).toBeInTheDocument()
  expect(container.querySelector("pre")!.textContent).toBe(value)
  expect(container.firstChild).toHaveClass("text-red-600")
})
