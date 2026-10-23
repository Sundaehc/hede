import { useState } from "react"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { ProductToolbar } from "@/components/product-admin/product-toolbar"

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  getProductImageRefreshStatus: vi.fn().mockResolvedValue({ in_progress: false }),
}))

function toolbarProps() {
  return {
    brand: "eblan" as const,
    year: "2026",
    value: "ER-DRAFT",
    query: "ER",
    prefixValue: "ER7-DRAFT",
    skuPrefix: "ER7",
    isLoading: false,
    canExport: true,
    canExportPrices: true,
    canImport: false,
    canRefreshImages: false,
    onValueChange: vi.fn(),
    onPrefixValueChange: vi.fn(),
    onSearch: vi.fn(),
    onClear: vi.fn(),
    onRefresh: vi.fn(),
    onImportComplete: vi.fn(),
    onMessage: vi.fn(),
  }
}

afterEach(cleanup)

test("keeps comma-separated searches compact and only grows for newlines", async () => {
  const props = toolbarProps()
  const { rerender } = render(<ProductToolbar {...props} value="ER1,ER2，ER3" />)
  await waitFor(() => expect(screen.getByRole("button", { name: "搜索" })).toBeEnabled())

  const search = screen.getByLabelText("包含搜索")
  expect(search).toHaveAttribute("rows", "1")
  expect(search).toHaveClass("min-h-8", "w-full", "min-w-0")
  expect(screen.getByLabelText("货号前缀")).toHaveClass("h-8", "w-full", "min-w-0")

  rerender(<ProductToolbar {...props} value={"ER1\nER2"} />)
  expect(search).toHaveAttribute("rows", "2")
  rerender(<ProductToolbar {...props} value={"ER1\nER2\nER3\nER4"} />)
  expect(search).toHaveAttribute("rows", "3")
})

test("flattens export groups and uses compact dates with responsive wrapping", async () => {
  render(<ProductToolbar {...toolbarProps()} onCreate={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole("button", { name: "搜索" })).toBeEnabled())

  const exports = screen.getByRole("group", { name: "数据导出" })
  const maintenance = screen.getByRole("group", { name: "商品维护" })
  const activity = screen.getByRole("group", { name: "按时间导出" })
  expect(exports.parentElement).toBe(activity.parentElement)
  expect(maintenance.parentElement).toBe(activity.parentElement)
  expect(activity.parentElement).toHaveClass("flex-wrap", "pt-2", "min-w-0")
  expect(activity).toHaveClass("flex-wrap", "max-w-full", "min-w-0")
  expect(activity).not.toHaveClass("border", "p-3", "rounded-xl")
  expect(activity).toHaveAccessibleDescription("仅包含所选时间内导入或新增的商品")
  expect(screen.getByText("仅包含所选时间内导入或新增的商品")).toHaveClass("sr-only")
  expect(screen.queryByText("数据导出")).not.toBeInTheDocument()
  expect(screen.queryByText("商品维护")).not.toBeInTheDocument()
  expect(screen.queryByRole("status")).not.toBeInTheDocument()
  expect(within(activity).getByRole("button", { name: /^导出时间段：/ })).toHaveClass("h-8", "max-w-full")
  for (const group of [exports, maintenance, activity]) {
    for (const button of within(group).getAllByRole("button")) {
      if (button.textContent?.includes("导出") || button.textContent === "新增商品") {
        expect(button).toHaveClass("h-8")
      }
    }
  }
})

test("preserves search shortcuts and toolbar actions in compact mode", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  const onSearch = vi.fn()
  const onOpenLogs = vi.fn()
  const onOpenRecycleBin = vi.fn()
  function ToolbarHarness() {
    const [value, setValue] = useState("")
    const [prefixValue, setPrefixValue] = useState("")
    return <ProductToolbar {...props} value={value} prefixValue={prefixValue} onValueChange={setValue} onPrefixValueChange={setPrefixValue} onSearch={() => onSearch(value, prefixValue)} onOpenLogs={onOpenLogs} onOpenRecycleBin={onOpenRecycleBin} />
  }
  render(<ToolbarHarness />)
  await user.type(screen.getByLabelText("包含搜索"), "ER1,ER2{enter}")
  expect(onSearch).toHaveBeenCalledExactlyOnceWith("ER1,ER2", "")
  await user.keyboard("{Shift>}{Enter}{/Shift}ER3")
  expect(onSearch).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText("包含搜索")).toHaveValue("ER1,ER2\nER3")
  await user.type(screen.getByLabelText("货号前缀"), "ER7{enter}")
  expect(onSearch).toHaveBeenLastCalledWith("ER1,ER2\nER3", "ER7")
  expect(onSearch).toHaveBeenCalledTimes(2)
  await user.click(screen.getByRole("button", { name: "清空" }))
  await user.click(screen.getByRole("button", { name: "刷新" }))
  await user.click(screen.getByRole("button", { name: "操作日志" }))
  await user.click(screen.getByRole("button", { name: "回收站" }))
  expect(props.onClear).toHaveBeenCalledTimes(1)
  expect(props.onRefresh).toHaveBeenCalledTimes(1)
  expect(onOpenLogs).toHaveBeenCalledTimes(1)
  expect(onOpenRecycleBin).toHaveBeenCalledTimes(1)
})

test("collapses the full search and export area without changing filters", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  render(<ProductToolbar {...props} />)
  const toggle = screen.getByRole("button", { name: "收起搜索区" })
  const content = document.getElementById(toggle.getAttribute("aria-controls") || "")
  expect(toggle).toHaveAttribute("aria-expanded", "true")
  expect(content).toBeVisible()
  expect(screen.getByLabelText("包含搜索")).toBeVisible()
  expect(screen.getByRole("group", { name: "数据导出" })).toBeVisible()
  expect(screen.getByRole("group", { name: "按时间导出" })).toBeVisible()

  await user.click(toggle)
  expect(screen.getByRole("button", { name: "展开搜索区" })).toHaveAttribute("aria-expanded", "false")
  expect(content).not.toBeVisible()
  expect(screen.getByLabelText("包含搜索")).not.toBeVisible()
  expect(screen.queryByRole("button", { name: "搜索" })).not.toBeInTheDocument()
  expect(screen.queryByRole("group", { name: "数据导出" })).not.toBeInTheDocument()
  expect(screen.queryByRole("group", { name: "按时间导出" })).not.toBeInTheDocument()
  expect(screen.getByText("2 项条件")).toBeVisible()
  const summary = screen.getByRole("group", { name: "当前搜索条件" })
  expect(summary).toHaveAttribute("title", "包含：ER；前缀：ER7")
  expect(within(summary).getByText("ER")).toBeInTheDocument()
  expect(within(summary).getByText("ER7")).toBeInTheDocument()
  expect(within(summary).queryByText("ER-DRAFT")).not.toBeInTheDocument()
  expect(props.onValueChange).not.toHaveBeenCalled()
  expect(props.onPrefixValueChange).not.toHaveBeenCalled()
  expect(props.onSearch).not.toHaveBeenCalled()
  expect(props.onClear).not.toHaveBeenCalled()

  await user.click(screen.getByRole("button", { name: "展开搜索区" }))
  expect(screen.getByLabelText("包含搜索")).toHaveValue("ER-DRAFT")
  expect(screen.getByLabelText("货号前缀")).toHaveValue("ER7-DRAFT")
  expect(screen.getByRole("group", { name: "按时间导出" })).toBeVisible()
})

test("preserves edited drafts and activity dates while collapsed", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  const onSearch = vi.fn()
  function ToolbarHarness() {
    const [value, setValue] = useState("")
    const [prefixValue, setPrefixValue] = useState("")
    return <ProductToolbar {...props} value={value} prefixValue={prefixValue} onValueChange={setValue} onPrefixValueChange={setPrefixValue} onSearch={() => onSearch(value, prefixValue)} />
  }
  render(<ToolbarHarness />)
  await user.type(screen.getByLabelText("包含搜索"), "ER123")
  await user.type(screen.getByLabelText("货号前缀"), "ER7")
  await user.click(screen.getByRole("button", { name: /^导出时间段：/ }))
  fireEvent.change(screen.getByLabelText("导出时间段开始日期"), { target: { value: "2026-01-05" } })
  fireEvent.change(screen.getByLabelText("导出时间段结束日期"), { target: { value: "2026-01-08" } })
  await user.click(screen.getByRole("button", { name: "收起搜索区" }))
  await user.click(screen.getByRole("button", { name: "展开搜索区" }))
  expect(screen.getByLabelText("包含搜索")).toHaveValue("ER123")
  expect(screen.getByLabelText("货号前缀")).toHaveValue("ER7")
  expect(screen.getByLabelText("导出时间段开始日期")).toHaveValue("2026-01-05")
  expect(screen.getByLabelText("导出时间段结束日期")).toHaveValue("2026-01-08")
  await user.click(screen.getByRole("button", { name: "搜索" }))
  expect(onSearch).toHaveBeenCalledExactlyOnceWith("ER123", "ER7")
})

test("remembers the collapsed state across remounts and brand switches", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  const first = render(<ProductToolbar {...props} />)
  await user.click(screen.getByRole("button", { name: "收起搜索区" }))
  first.rerender(<ProductToolbar {...props} brand="cbanner_mens" />)
  expect(screen.getByRole("button", { name: "展开搜索区" })).toHaveAttribute("aria-expanded", "false")
  first.unmount()
  render(<ProductToolbar {...props} />)
  expect(screen.getByRole("button", { name: "展开搜索区" })).toHaveAttribute("aria-expanded", "false")
  expect(screen.getByLabelText("包含搜索")).not.toBeVisible()
  await user.click(screen.getByRole("button", { name: "展开搜索区" }))
  expect(screen.getByLabelText("包含搜索")).toBeVisible()
})

test("allows toggling for read-only users while data is loading", async () => {
  const user = userEvent.setup()
  render(<ProductToolbar {...toolbarProps()} isLoading canExport={false} canExportPrices={false} />)
  const toggle = screen.getByRole("button", { name: "收起搜索区" })
  expect(toggle).toBeEnabled()
  await user.click(toggle)
  expect(screen.getByRole("button", { name: "展开搜索区" })).toBeEnabled()
  expect(screen.getByLabelText("包含搜索")).not.toBeVisible()
  await user.click(screen.getByRole("button", { name: "展开搜索区" }))
  expect(screen.getByLabelText("包含搜索")).toBeVisible()
  expect(screen.queryByRole("group", { name: "数据导出" })).not.toBeInTheDocument()
})

test("uses a compact outlined toggle with keyboard support and a rotating indicator", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  render(<ProductToolbar {...props} />)
  const toggle = screen.getByRole("button", { name: "收起搜索区" })
  expect(toggle).toHaveClass("h-7", "rounded-md", "border-border/80", "bg-background")
  expect(toggle).toHaveAttribute("title", "收起搜索与导出工具，保留当前搜索条件")
  expect(toggle.querySelector("svg")).toHaveClass("rotate-180", "motion-reduce:transition-none")
  expect(toggle.querySelector("svg")).toHaveAttribute("aria-hidden", "true")

  toggle.focus()
  await user.keyboard("{Enter}")
  expect(toggle).toHaveFocus()
  expect(toggle).toHaveAccessibleName("展开搜索区")
  expect(toggle).toHaveAttribute("aria-expanded", "false")
  expect(toggle.querySelector("svg")).toHaveClass("rotate-0")

  await user.keyboard(" ")
  expect(toggle).toHaveAccessibleName("收起搜索区")
  expect(toggle).toHaveAttribute("aria-expanded", "true")
  expect(screen.queryByRole("group", { name: "当前搜索条件" })).not.toBeInTheDocument()
  expect(props.onSearch).not.toHaveBeenCalled()
})

test("only summarizes submitted filters and keeps complete values in compact chip titles", async () => {
  const user = userEvent.setup()
  const props = toolbarProps()
  const longQuery = "ER1234567890".repeat(12)
  const { rerender } = render(<ProductToolbar {...props} query={`  ${longQuery}\nER2  `} skuPrefix="  " />)
  await user.click(screen.getByRole("button", { name: "收起搜索区" }))
  expect(screen.getByText("1 项条件")).toBeVisible()
  const summary = screen.getByRole("group", { name: "当前搜索条件" })
  expect(summary).toHaveClass("min-w-0", "hidden", "sm:flex")
  expect(summary).toHaveAttribute("title", `包含：${longQuery} ER2`)
  const filterValue = within(summary).getByText(`${longQuery} ER2`)
  expect(filterValue).toHaveClass("truncate")
  expect(filterValue.parentElement).toHaveAttribute("title", `包含：${longQuery} ER2`)
  expect(within(summary).queryByText("前缀")).not.toBeInTheDocument()

  rerender(<ProductToolbar {...props} query="" skuPrefix="" />)
  expect(screen.getByText("未设置搜索条件")).toBeInTheDocument()
  expect(screen.queryByRole("group", { name: "当前搜索条件" })).not.toBeInTheDocument()
  expect(screen.queryByText(/项条件$/)).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "展开搜索区" })).toBeEnabled()
})
