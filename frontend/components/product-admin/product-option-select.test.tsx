import { useState } from "react"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import {
  ProductOptionSelect,
  type ProductSelectOption,
} from "@/components/product-admin/product-option-select"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"

const options: ProductSelectOption[] = [
  { value: "01", label: "01", description: "黑色" },
  { value: "02", label: "02", description: "白色", keywords: "浅色" },
  { value: "03", label: "03", description: "棕色" },
]

function Fixture({
  initialValue = "01",
  items = options,
  onChange = vi.fn(),
  onSubmit = vi.fn(),
  onOpenChange = vi.fn(),
  allowCustomValue = false,
  disabled = false,
}: {
  initialValue?: string
  items?: ProductSelectOption[]
  onChange?: (value: string) => void
  onSubmit?: () => void
  onOpenChange?: (open: boolean) => void
  allowCustomValue?: boolean
  disabled?: boolean
}) {
  const [value, setValue] = useState(initialValue)
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>编辑商品</DialogTitle>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit()
          }}
        >
          <label htmlFor="color-option">颜色代码</label>
          <ProductOptionSelect
            id="color-option"
            label="颜色代码"
            value={value}
            options={items}
            disabled={disabled}
            allowCustomValue={allowCustomValue}
            onValueChange={(next) => {
              setValue(next)
              onChange(next)
            }}
          />
          <label htmlFor="sku">商品货号</label>
          <input id="sku" defaultValue="TEST" />
          <button type="submit">保存</button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

afterEach(cleanup)

test("renders a compact portal inside the form, marks selection and saves an option", async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Fixture onChange={onChange} />)
  const input = screen.getByRole("combobox", { name: "颜色代码" })
  await user.click(input)
  const panel = screen.getByRole("dialog", { name: "选择颜色代码" })
  expect(panel.closest('[data-slot="dialog-content"]')).toBe(
    screen.getByRole("dialog", { name: "编辑商品" })
  )
  expect(panel).toHaveClass(
    "max-h-[min(18rem,var(--radix-popover-content-available-height))]",
    "w-[var(--radix-popover-trigger-width)]"
  )
  expect(screen.getByRole("listbox")).toHaveClass(
    "overflow-y-auto",
    "overscroll-contain"
  )
  expect(screen.getByRole("option", { name: "01 黑色" })).toHaveAttribute(
    "aria-selected",
    "true"
  )
  expect(input).toHaveFocus()
  await user.click(screen.getByRole("option", { name: "02 白色" }))
  expect(input).toHaveValue("02 - 白色")
  expect(onChange).toHaveBeenCalledExactlyOnceWith("02")
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
})

test("supports keyboard selection and Escape without closing the product form", async () => {
  const user = userEvent.setup()
  const onOpenChange = vi.fn()
  render(<Fixture onOpenChange={onOpenChange} />)
  const input = screen.getByLabelText("颜色代码")
  await user.click(input)
  await user.keyboard("{End}")
  expect(
    document.getElementById(input.getAttribute("aria-activedescendant")!)
  ).toHaveTextContent("棕色")
  await user.keyboard("{Home}{ArrowDown}{Enter}")
  expect(input).toHaveValue("02 - 白色")
  await user.click(input)
  await user.keyboard("{Escape}")
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  expect(onOpenChange).not.toHaveBeenCalled()
})

test("searches labels and keywords without saving unmatched input or submitting the form", async () => {
  const user = userEvent.setup()
  const onSubmit = vi.fn()
  const onChange = vi.fn()
  render(<Fixture onSubmit={onSubmit} onChange={onChange} />)
  const input = screen.getByLabelText("颜色代码")
  await user.click(input)
  await user.type(input, "浅色")
  expect(screen.getAllByRole("option")).toHaveLength(1)
  expect(screen.getByRole("option")).toHaveTextContent("白色")
  await user.clear(input)
  await user.type(input, "不存在{Enter}")
  expect(screen.getByRole("status")).toHaveTextContent("没有匹配的选项")
  expect(onSubmit).not.toHaveBeenCalled()
  expect(onChange).not.toHaveBeenCalled()
  await user.click(screen.getByLabelText("商品货号"))
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  expect(input).toHaveValue("01 - 黑色")
})

test("clears only the selection and retains custom value support", async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Fixture allowCustomValue onChange={onChange} />)
  await user.click(screen.getByRole("button", { name: "清空颜色代码" }))
  expect(screen.getByLabelText("颜色代码")).toHaveValue("")
  await user.click(screen.getByLabelText("颜色代码"))
  await user.type(screen.getByLabelText("颜色代码"), "自定义")
  await user.keyboard("{Escape}")
  expect(screen.getByLabelText("颜色代码")).toHaveValue("自定义")
  expect(screen.getByLabelText("商品货号")).toHaveValue("TEST")
})

test("ignores confirmation during Chinese composition and Tab moves to the next form field", async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Fixture onChange={onChange} />)
  const input = screen.getByLabelText("颜色代码")
  await user.click(input)
  fireEvent.keyDown(input, { key: "Enter", isComposing: true })
  expect(onChange).not.toHaveBeenCalled()
  expect(screen.getByRole("listbox")).toBeInTheDocument()
  await user.tab()
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "清空颜色代码" })).toHaveFocus()
  )
})

test("can search beyond the first page of options and keeps unavailable saved values", async () => {
  const user = userEvent.setup()
  const items = Array.from({ length: 120 }, (_, index) => ({
    value: `材料${index + 1}`,
    label: `材料${index + 1}`,
  }))
  render(<Fixture initialValue="旧值" items={items} />)
  const input = screen.getByLabelText("颜色代码")
  await user.keyboard("{Escape}")
  expect(input).toHaveValue("旧值")
  await user.click(input)
  expect(
    within(screen.getByRole("listbox")).getAllByRole("option")
  ).toHaveLength(80)
  await user.type(input, "材料120")
  await user.click(screen.getByRole("option", { name: "材料120" }))
  expect(input).toHaveValue("材料120")
})

test("does not open a disabled selector", async () => {
  const user = userEvent.setup()
  render(<Fixture disabled />)
  expect(screen.getByLabelText("颜色代码")).toBeDisabled()
  await user.click(screen.getByLabelText("颜色代码"))
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
})
