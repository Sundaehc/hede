import { useState } from "react"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { AccountSubjectSelect } from "@/components/inventory-admin/account-subject-select"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import type { InventoryAccountSubject } from "@/lib/api"

const subjects = [
  { id: 1, code: null, name: "优惠收入", category: "收入类", created_at: null, updated_at: null },
  { id: 2, code: null, name: "大底收入", category: "收入类", created_at: null, updated_at: null },
  { id: 3, code: null, name: "包装费用", category: "支出类", created_at: null, updated_at: null },
  { id: 4, code: null, name: "鞋花费用", category: "支出类", created_at: null, updated_at: null },
] satisfies InventoryAccountSubject[]

function Fixture({ initialValue = "", options = subjects, disabled = false }: {
  initialValue?: string
  options?: InventoryAccountSubject[]
  disabled?: boolean
}) {
  const [value, setValue] = useState(initialValue)
  return (
    <Dialog open>
      <DialogContent>
        <DialogTitle>新增明细</DialogTitle>
        <label htmlFor="subject">费用项目名 / 科目</label>
        <AccountSubjectSelect id="subject" value={value} subjects={options} onValueChange={setValue} disabled={disabled} />
        <label htmlFor="amount">金额</label>
        <input id="amount" defaultValue="681" />
        <button type="button">保存</button>
      </DialogContent>
    </Dialog>
  )
}

afterEach(cleanup)

test("renders a bounded grouped panel inside the form dialog and retains the selected subject", async () => {
  const user = userEvent.setup()
  render(<Fixture initialValue="包装费用" />)
  const trigger = screen.getByLabelText("费用项目名 / 科目")
  expect(trigger).toHaveTextContent("包装费用")
  await user.click(trigger)

  const panel = screen.getByRole("dialog", { name: "选择费用科目" })
  expect(panel).toHaveClass("max-h-[min(22rem,var(--radix-popover-content-available-height))]", "w-[var(--radix-popover-trigger-width)]", "max-w-[calc(100vw-1.5rem)]")
  expect(panel.closest('[data-slot="dialog-content"]')).toBe(screen.getByRole("dialog", { name: "新增明细" }))
  expect(screen.getByRole("listbox", { name: "费用科目" })).toHaveClass("overflow-y-auto", "min-h-0")
  expect(screen.getByRole("group", { name: "收入类" })).toBeInTheDocument()
  expect(screen.getByRole("group", { name: "支出类" })).toBeInTheDocument()
  expect(screen.getByRole("option", { name: "包装费用" })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByText("共 4 个科目")).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole("combobox", { name: "搜索科目" })).toHaveFocus())

  await user.click(screen.getByRole("option", { name: "优惠收入" }))
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  expect(trigger).toHaveTextContent("优惠收入")
  expect(screen.getByLabelText("金额")).toHaveValue("681")
  await waitFor(() => expect(trigger).toHaveFocus())
})

test("keeps category headers in the scrolling list without pinning them above other categories", async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  await user.click(screen.getByLabelText("费用项目名 / 科目"))
  const list = screen.getByRole("listbox", { name: "费用科目" })
  for (const category of ["收入类", "支出类"]) {
    const group = within(list).getByRole("group", { name: category })
    const header = within(group).getByText(category).parentElement!
    expect(header.parentElement).toBe(group)
    expect(header).not.toHaveClass("sticky")
    expect(header).not.toHaveClass("fixed")
  }
})

test("searches names and categories and supports an empty result and clearing search", async () => {
  const user = userEvent.setup()
  render(<Fixture initialValue="大底收入" />)
  await user.click(screen.getByLabelText("费用项目名 / 科目"))
  const search = screen.getByRole("combobox", { name: "搜索科目" })
  await user.type(search, "支出类")
  expect(screen.getAllByRole("option")).toHaveLength(2)
  expect(screen.queryByRole("group", { name: "收入类" })).not.toBeInTheDocument()
  await user.clear(search)
  await user.type(search, "包装")
  expect(screen.getAllByRole("option")).toHaveLength(1)
  await user.clear(search)
  await user.type(search, "不存在")
  expect(screen.queryByRole("option")).not.toBeInTheDocument()
  expect(screen.getByText("没有匹配的科目，请更换关键词")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "清空科目搜索" }))
  expect(search).toHaveValue("")
  expect(search).toHaveFocus()
  expect(screen.getAllByRole("option")).toHaveLength(4)
  expect(screen.getByRole("option", { name: "大底收入" })).toHaveAttribute("aria-selected", "true")
})

test("supports arrow keys and Enter without submitting the parent form", async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  const trigger = screen.getByLabelText("费用项目名 / 科目")
  trigger.focus()
  await user.keyboard("{ArrowDown}")
  const search = await screen.findByRole("combobox", { name: "搜索科目" })
  await waitFor(() => expect(search).toHaveFocus())
  expect(search).toHaveAttribute("aria-activedescendant", screen.getByRole("option", { name: "优惠收入" }).id)
  await user.keyboard("{ArrowDown}")
  expect(search).toHaveAttribute("aria-activedescendant", screen.getByRole("option", { name: "大底收入" }).id)
  await user.keyboard("{ArrowUp}{ArrowDown}{Enter}")
  expect(trigger).toHaveTextContent("大底收入")
  expect(screen.getByRole("dialog", { name: "新增明细" })).toBeInTheDocument()
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
})

test("Escape dismisses only the dropdown and discards unfinished search", async () => {
  const user = userEvent.setup()
  render(<Fixture initialValue="包装费用" />)
  const trigger = screen.getByLabelText("费用项目名 / 科目")
  await user.click(trigger)
  await user.type(screen.getByRole("combobox", { name: "搜索科目" }), "优惠")
  await user.keyboard("{Escape}")
  expect(screen.getByRole("dialog", { name: "新增明细" })).toBeInTheDocument()
  expect(trigger).toHaveTextContent("包装费用")
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  await user.click(trigger)
  expect(screen.getByRole("combobox", { name: "搜索科目" })).toHaveValue("")
  expect(screen.getAllByRole("option")).toHaveLength(4)
})

test("outside focus closes the panel without stealing focus from another form field", async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  await user.click(screen.getByLabelText("费用项目名 / 科目"))
  await user.click(screen.getByLabelText("金额"))
  await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument())
  expect(screen.getByLabelText("金额")).toHaveFocus()
})

test("shows helpful empty data, preserves legacy names and disables interaction when requested", async () => {
  const user = userEvent.setup()
  const { rerender } = render(<Fixture options={[]} initialValue="旧科目" />)
  const trigger = screen.getByLabelText("费用项目名 / 科目")
  expect(trigger).toHaveTextContent("旧科目")
  await user.click(trigger)
  expect(screen.getByText("暂无可选科目，请先在科目管理中添加")).toBeInTheDocument()
  await user.keyboard("{Escape}")
  rerender(<Fixture options={[]} disabled />)
  expect(trigger).toBeDisabled()
  await user.click(trigger)
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
})

test("does not commit a subject while confirming Chinese input composition", async () => {
  const user = userEvent.setup()
  const onValueChange = vi.fn()
  render(<AccountSubjectSelect id="subject" value="" subjects={subjects} onValueChange={onValueChange} />)
  await user.click(screen.getByRole("button", { name: "请选择科目" }))
  const search = screen.getByRole("combobox", { name: "搜索科目" })
  fireEvent.keyDown(search, { key: "Enter", isComposing: true })
  expect(onValueChange).not.toHaveBeenCalled()
  expect(within(screen.getByRole("listbox")).getAllByRole("option")).toHaveLength(4)
})
