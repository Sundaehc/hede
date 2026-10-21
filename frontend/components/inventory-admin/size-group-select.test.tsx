import { useState } from "react"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { SizeGroupSelect } from "@/components/inventory-admin/size-group-select"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import type { SizeGroup } from "@/lib/types"

const groups: SizeGroup[] = [
  { id: 1, name: "女鞋尺码组220-250", product_count: 0, items: ["220", "225", "230", "235", "240", "245", "250"].map((size, index) => ({ id: index, size_name: size, barcode: size, sort_order: index })) },
  { id: 2, name: "男鞋尺码组240-270", product_count: 0, items: ["240", "245", "250", "255", "260", "265", "270"].map((size, index) => ({ id: index + 10, size_name: size, barcode: size, sort_order: index })) },
  { id: 3, name: "标准女鞋", product_count: 0, items: [{ id: 20, size_name: "35", barcode: "35", sort_order: 0 }] },
]

function Fixture({ initialValue = "", options = groups, disabled = false, onChange = () => {} }: {
  initialValue?: string
  options?: SizeGroup[]
  disabled?: boolean
  onChange?: (value: string) => void
}) {
  const [value, setValue] = useState(initialValue)
  return (
    <Dialog open>
      <DialogContent>
        <DialogTitle>编辑明细</DialogTitle>
        <label htmlFor="size-range">尺码段</label>
        <SizeGroupSelect id="size-range" value={value} groups={options} disabled={disabled} onValueChange={(next) => {
          setValue(next)
          onChange(next)
        }} />
        <label htmlFor="quantity">数量</label>
        <input id="quantity" defaultValue="1" />
        <button type="button">保存</button>
      </DialogContent>
    </Dialog>
  )
}

afterEach(cleanup)

test("opens a compact scrolling dropdown inside the edit dialog and marks the current group", async () => {
  const user = userEvent.setup()
  render(<Fixture initialValue="女鞋尺码组220-250" />)
  const trigger = screen.getByLabelText("尺码段")
  expect(trigger).toHaveClass("h-9", "min-w-0")
  expect(trigger).toHaveTextContent("女鞋尺码组220-250")
  expect(trigger).toHaveTextContent("7 码")
  await user.click(trigger)
  const panel = screen.getByRole("dialog", { name: "选择尺码段" })
  expect(panel).toHaveClass("max-h-[min(20rem,var(--radix-popover-content-available-height))]", "w-[var(--radix-popover-trigger-width)]", "max-w-[calc(100vw-1.5rem)]")
  expect(panel.closest('[data-slot="dialog-content"]')).toBe(screen.getByRole("dialog", { name: "编辑明细" }))
  expect(screen.getByRole("listbox", { name: "尺码段选项" })).toHaveClass("overflow-y-auto", "overscroll-contain")
  expect(screen.getByRole("option", { name: "女鞋尺码组220-250 7 码" })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByText("共 3 个尺码段")).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole("combobox", { name: "搜索尺码段" })).toHaveFocus())
  await user.click(screen.getByRole("option", { name: "男鞋尺码组240-270 7 码" }))
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  expect(trigger).toHaveTextContent("男鞋尺码组240-270")
  expect(screen.getByLabelText("数量")).toHaveValue("1")
  await waitFor(() => expect(trigger).toHaveFocus())
})

test("searches both group names and member sizes, handles no results and clears search", async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  await user.click(screen.getByLabelText("尺码段"))
  const search = screen.getByRole("combobox", { name: "搜索尺码段" })
  await user.type(search, "女鞋 220")
  expect(screen.getAllByRole("option")).toHaveLength(1)
  expect(screen.getByRole("option")).toHaveTextContent("女鞋尺码组220-250")
  await user.clear(search)
  await user.type(search, "35")
  expect(screen.getByRole("option", { name: "标准女鞋 1 码" })).toBeInTheDocument()
  await user.clear(search)
  await user.type(search, "不存在")
  expect(screen.queryByRole("option")).not.toBeInTheDocument()
  expect(screen.getByRole("status")).toHaveTextContent("没有匹配的尺码段")
  await user.click(screen.getByRole("button", { name: "清空尺码段搜索" }))
  expect(search).toHaveValue("")
  expect(screen.getAllByRole("option")).toHaveLength(4)
  expect(search).toHaveFocus()
})

test("supports keyboard navigation, confirmation and Escape without closing the form", async () => {
  const user = userEvent.setup()
  render(<Fixture initialValue="女鞋尺码组220-250" />)
  const trigger = screen.getByLabelText("尺码段")
  trigger.focus()
  await user.keyboard("{ArrowDown}")
  const search = screen.getByRole("combobox", { name: "搜索尺码段" })
  await waitFor(() => expect(search).toHaveFocus())
  await user.keyboard("{ArrowDown}")
  expect(document.getElementById(search.getAttribute("aria-activedescendant")!)).toHaveTextContent("男鞋尺码组240-270")
  await user.keyboard("{End}")
  expect(document.getElementById(search.getAttribute("aria-activedescendant")!)).toHaveTextContent("标准女鞋")
  await user.keyboard("{Home}{ArrowDown}{ArrowDown}{Enter}")
  expect(trigger).toHaveTextContent("男鞋尺码组240-270")
  await user.click(trigger)
  await user.keyboard("{Escape}")
  expect(screen.queryByRole("dialog", { name: "选择尺码段" })).not.toBeInTheDocument()
  expect(screen.getByRole("dialog", { name: "编辑明细" })).toBeInTheDocument()
})

test("reselecting the current group does not reset quantities and clearing selection is explicit", async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Fixture initialValue="女鞋尺码组220-250" onChange={onChange} />)
  await user.click(screen.getByLabelText("尺码段"))
  await user.click(screen.getByRole("option", { name: "女鞋尺码组220-250 7 码" }))
  expect(onChange).not.toHaveBeenCalled()
  await user.click(screen.getByLabelText("尺码段"))
  await user.click(screen.getByRole("option", { name: "未选择尺码段" }))
  expect(onChange).toHaveBeenCalledExactlyOnceWith("")
  expect(screen.getByLabelText("尺码段")).toHaveTextContent("未选择尺码段")
})

test("keeps a saved group name visible when the option is no longer available", async () => {
  const user = userEvent.setup()
  render(<Fixture initialValue="历史尺码组" />)
  expect(screen.getByLabelText("尺码段")).toHaveTextContent("历史尺码组")
  await user.click(screen.getByLabelText("尺码段"))
  await user.keyboard("{Escape}")
  expect(screen.getByLabelText("尺码段")).toHaveTextContent("历史尺码组")
})

test("shows all options without truncating long lists", async () => {
  const user = userEvent.setup()
  const manyGroups = Array.from({ length: 120 }, (_, index) => ({ ...groups[0], id: index + 1, name: `尺码段${index + 1}` }))
  render(<Fixture options={manyGroups} initialValue="尺码段120" />)
  await user.click(screen.getByLabelText("尺码段"))
  expect(within(screen.getByRole("listbox")).getAllByRole("option")).toHaveLength(121)
  expect(screen.getByRole("option", { name: "尺码段120 7 码" })).toHaveAttribute("aria-selected", "true")
})

test("handles an empty option list and a disabled selector", async () => {
  const user = userEvent.setup()
  const rendered = render(<Fixture options={[]} />)
  await user.click(screen.getByLabelText("尺码段"))
  expect(screen.getByRole("status")).toHaveTextContent("暂无可选尺码段")
  expect(screen.getByRole("option", { name: "未选择尺码段" })).toBeInTheDocument()
  rendered.unmount()
  render(<Fixture disabled />)
  expect(screen.getByLabelText("尺码段")).toBeDisabled()
  await user.click(screen.getByLabelText("尺码段"))
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
})

test("does not confirm an option during Chinese input composition", async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Fixture onChange={onChange} />)
  await user.click(screen.getByLabelText("尺码段"))
  const search = screen.getByRole("combobox", { name: "搜索尺码段" })
  await user.type(search, "女鞋 220")
  fireEvent.keyDown(search, { key: "Enter", isComposing: true })
  expect(onChange).not.toHaveBeenCalled()
  expect(screen.getByRole("listbox")).toBeInTheDocument()
})

test("dismissing by clicking outside keeps the selected group and form intact", async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<Fixture initialValue="女鞋尺码组220-250" onChange={onChange} />)
  await user.click(screen.getByLabelText("尺码段"))
  await user.type(screen.getByRole("combobox", { name: "搜索尺码段" }), "男鞋")
  await user.click(screen.getByLabelText("数量"))
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  expect(screen.getByRole("dialog", { name: "编辑明细" })).toBeInTheDocument()
  expect(screen.getByLabelText("尺码段")).toHaveTextContent("女鞋尺码组220-250")
  expect(onChange).not.toHaveBeenCalled()
})
