import { useState, type ComponentProps } from "react"
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { DatePicker } from "@/components/ui/date-picker"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"

function Fixture({
  initialValue = "2026-10-16",
  ...props
}: Omit<ComponentProps<typeof DatePicker>, "value" | "onValueChange"> & {
  initialValue?: string
}) {
  const [value, setValue] = useState(initialValue)
  return (
    <DatePicker
      aria-label="业务日期"
      value={value}
      onValueChange={setValue}
      {...props}
    />
  )
}

function day(label: string) {
  return screen.getByRole("button", { name: label })
}

function openCalendar() {
  fireEvent.click(screen.getByRole("button", { name: "打开业务日期日历" }))
  return screen.getByRole("dialog", { name: "业务日期日历" })
}

afterEach(() => vi.useRealTimers())

describe("DatePicker", () => {
  it("renders a Chinese Monday-first calendar with selected and today states", () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date(2026, 9, 16, 12))
    render(<Fixture />)
    openCalendar()

    expect(screen.getByRole("grid", { name: "2026年10月" })).toBeInTheDocument()
    expect(
      screen.getAllByRole("columnheader").map((element) => element.textContent)
    ).toEqual(["一", "二", "三", "四", "五", "六", "日"])
    expect(screen.getAllByRole("gridcell")).toHaveLength(42)
    expect(day("2026年10月16日")).toHaveAttribute("aria-current", "date")
    expect(day("2026年10月16日").closest("td")).toHaveAttribute(
      "aria-selected",
      "true"
    )
  })

  it("opens from the input and selects a date without changing its format", async () => {
    render(<Fixture id="business-date" />)
    fireEvent.click(screen.getByLabelText("业务日期"))
    await waitFor(() => expect(day("2026年10月16日")).toHaveFocus())
    fireEvent.click(day("2026年10月21日"))
    expect(screen.getByLabelText("业务日期")).toHaveValue("2026-10-21")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("preserves manual date changes and rejects values outside its bounds", () => {
    render(<Fixture min="2026-10-10" max="2026-10-20" />)
    const input = screen.getByLabelText("业务日期")
    fireEvent.change(input, { target: { value: "2026-10-19" } })
    expect(input).toHaveValue("2026-10-19")
    fireEvent.change(input, { target: { value: "2026-10-21" } })
    expect(input).toHaveValue("2026-10-19")
    expect(input).toHaveAttribute("min", "2026-10-10")
    expect(input).toHaveAttribute("max", "2026-10-20")
  })

  it("disables out-of-range dates and month navigation", () => {
    render(<Fixture min="2026-10-10" max="2026-10-20" />)
    openCalendar()
    expect(day("2026年10月9日")).toBeDisabled()
    expect(day("2026年10月21日")).toBeDisabled()
    expect(day("2026年10月10日")).toBeEnabled()
    expect(screen.getByRole("button", { name: "上个月" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "下个月" })).toBeDisabled()
    expect(
      within(screen.getByLabelText("选择月份")).getByRole("option", {
        name: "9月",
      })
    ).toBeDisabled()
  })

  it("switches months across year boundaries and retains a tabbable day", () => {
    render(<Fixture initialValue="2026-12-31" />)
    openCalendar()
    fireEvent.click(screen.getByRole("button", { name: "下个月" }))
    expect(screen.getByRole("grid", { name: "2027年1月" })).toBeInTheDocument()
    expect(day("2027年1月1日")).toHaveAttribute("tabindex", "0")
    fireEvent.click(screen.getByRole("button", { name: "上个月" }))
    expect(screen.getByRole("grid", { name: "2026年12月" })).toBeInTheDocument()
  })

  it("clamps the month when switching to a boundary year", () => {
    render(
      <Fixture initialValue="2026-01-16" min="2025-05-10" max="2026-10-20" />
    )
    openCalendar()
    fireEvent.change(screen.getByLabelText("选择年份"), {
      target: { value: "2025" },
    })
    expect(screen.getByRole("grid", { name: "2025年5月" })).toBeInTheDocument()
    expect(day("2025年5月10日")).toHaveAttribute("tabindex", "0")
    fireEvent.change(screen.getByLabelText("选择月份"), {
      target: { value: "11" },
    })
    fireEvent.change(screen.getByLabelText("选择年份"), {
      target: { value: "2026" },
    })
    expect(screen.getByRole("grid", { name: "2026年10月" })).toBeInTheDocument()
  })

  it("supports leap days and does not overflow a short month on PageDown", async () => {
    render(<Fixture initialValue="2024-01-31" />)
    openCalendar()
    await waitFor(() => expect(day("2024年1月31日")).toHaveFocus())
    fireEvent.keyDown(day("2024年1月31日"), { key: "PageDown" })
    await waitFor(() => expect(day("2024年2月29日")).toHaveFocus())
    await userEvent.keyboard("{Enter}")
    expect(screen.getByLabelText("业务日期")).toHaveValue("2024-02-29")
  })

  it("supports arrow, week boundary, month and year keyboard navigation", async () => {
    render(<Fixture />)
    openCalendar()
    await waitFor(() => expect(day("2026年10月16日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" })
    await waitFor(() => expect(day("2026年10月17日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, { key: "Home" })
    await waitFor(() => expect(day("2026年10月12日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, { key: "End" })
    await waitFor(() => expect(day("2026年10月18日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" })
    await waitFor(() => expect(day("2026年10月25日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" })
    await waitFor(() => expect(day("2026年10月18日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, {
      key: "PageUp",
      shiftKey: true,
    })
    await waitFor(() => expect(day("2025年10月18日")).toHaveFocus())
  })

  it("opens with the keyboard without submitting its surrounding form", () => {
    const onSubmit = vi.fn((event) => event.preventDefault())
    render(
      <form onSubmit={onSubmit}>
        <Fixture />
      </form>
    )
    fireEvent.keyDown(screen.getByLabelText("业务日期"), { key: "Enter" })
    expect(
      screen.getByRole("dialog", { name: "业务日期日历" })
    ).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("only enables actual snapshot dates and skips unavailable dates with the keyboard", async () => {
    render(
      <Fixture
        initialValue="2026-10-09"
        availableDates={["2026-10-09", "2026-10-13", "2026-10-16", "invalid"]}
      />
    )
    openCalendar()
    expect(day("2026年10月10日")).toBeDisabled()
    expect(day("2026年10月13日")).toBeEnabled()
    fireEvent.keyDown(day("2026年10月9日"), { key: "ArrowRight" })
    await waitFor(() => expect(day("2026年10月13日")).toHaveFocus())
    fireEvent.click(day("2026年10月13日"))
    expect(screen.getByLabelText("业务日期")).toHaveValue("2026-10-13")
  })

  it("shows an empty state when no snapshot is available", () => {
    render(<Fixture availableDates={[]} />)
    openCalendar()
    expect(screen.getByText("暂无可选日期")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "今天" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "下个月" })).toBeDisabled()
    expect(
      screen
        .getAllByRole("gridcell")
        .every((cell) =>
          within(cell).getByRole("button").hasAttribute("disabled")
        )
    ).toBe(true)
  })

  it("can select today and clear an optional value", () => {
    vi.useFakeTimers({ toFake: ["Date"] })
    vi.setSystemTime(new Date(2026, 9, 16, 12))
    render(<Fixture initialValue="2026-10-01" />)
    openCalendar()
    fireEvent.click(screen.getByRole("button", { name: "今天" }))
    expect(screen.getByLabelText("业务日期")).toHaveValue("2026-10-16")
    openCalendar()
    fireEvent.click(screen.getByRole("button", { name: "清除" }))
    expect(screen.getByLabelText("业务日期")).toHaveValue("")
  })

  it("cannot clear a required value", () => {
    render(<Fixture required />)
    openCalendar()
    expect(screen.getByRole("button", { name: "清除" })).toBeDisabled()
  })

  it.each([{ disabled: true }, { readOnly: true }])(
    "does not open when disabled or read-only: %o",
    (props) => {
      render(<Fixture {...props} />)
      fireEvent.click(screen.getByLabelText("业务日期"))
      fireEvent.keyDown(screen.getByLabelText("业务日期"), { key: "ArrowDown" })
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      expect(
        screen.getByRole("button", { name: "打开业务日期日历" })
      ).toBeDisabled()
    }
  )

  it("closes on Escape and restores focus to its trigger", async () => {
    render(<Fixture />)
    openCalendar()
    await waitFor(() => expect(day("2026年10月16日")).toHaveFocus())
    fireEvent.keyDown(document.activeElement!, { key: "Escape" })
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "打开业务日期日历" })
      ).toHaveFocus()
    )
  })

  it("closes on an outside click without changing the value", async () => {
    render(
      <>
        <Fixture />
        <button type="button">其他操作</button>
      </>
    )
    openCalendar()
    await userEvent.click(screen.getByRole("button", { name: "其他操作" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByLabelText("业务日期")).toHaveValue("2026-10-16")
  })

  it("supports an existing history button as its trigger", () => {
    render(<Fixture trigger={<button type="button">选择历史快照</button>} />)
    fireEvent.click(screen.getByRole("button", { name: "选择历史快照" }))
    fireEvent.click(day("2026年10月15日"))
    fireEvent.click(screen.getByRole("button", { name: "选择历史快照" }))
    expect(day("2026年10月15日").closest("td")).toHaveAttribute(
      "aria-selected",
      "true"
    )
  })

  it("keeps focus inside a parent dialog and Escape closes only the calendar", async () => {
    const onOpenChange = vi.fn()
    render(
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogTitle>编辑单据</DialogTitle>
          <Fixture />
        </DialogContent>
      </Dialog>
    )
    const parent = screen.getByRole("dialog", { name: "编辑单据" })
    const calendar = openCalendar()
    expect(parent).toContainElement(calendar)
    await waitFor(() => expect(day("2026年10月16日")).toHaveFocus())
    fireEvent.keyDown(day("2026年10月16日"), { key: "Escape" })
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "业务日期日历" })
      ).not.toBeInTheDocument()
    )
    expect(onOpenChange).not.toHaveBeenCalled()
    openCalendar()
    fireEvent.click(day("2026年10月18日"))
    expect(screen.getByLabelText("业务日期")).toHaveValue("2026-10-18")
    expect(parent).toBeInTheDocument()
  })
})
