import { fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { DateRangeControl } from "@/components/ui/date-range-control"

function RangeFixture({ initialStart = "", initialEnd = "", maxDate }: { initialStart?: string; initialEnd?: string; maxDate?: string }) {
  const [start, setStart] = useState(initialStart)
  const [end, setEnd] = useState(initialEnd)

  return <DateRangeControl start={start} end={end} onStartChange={setStart} onEndChange={setEnd} maxDate={maxDate} />
}

describe("DateRangeControl", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2027, 1, 1, 12))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("selects and shifts natural weeks across year boundaries", () => {
    render(<RangeFixture initialStart="2026-12-31" initialEnd="2026-12-31" />)

    fireEvent.click(screen.getByRole("button", { name: "周" }))
    expect(screen.getByRole("button", { name: /2026-12-28至2027-01-03/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "周" })).toHaveAttribute("aria-pressed", "true")

    fireEvent.click(screen.getByRole("button", { name: "下一周期" }))
    expect(screen.getByRole("button", { name: /2027-01-04至2027-01-10/ })).toBeInTheDocument()
  })

  it("shifts whole calendar months without losing their last day", () => {
    render(<RangeFixture initialStart="2024-02-01" initialEnd="2024-02-29" />)

    fireEvent.click(screen.getByRole("button", { name: "下一周期" }))
    expect(screen.getByRole("button", { name: /2024-03-01至2024-03-31/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "上一周期" }))
    expect(screen.getByRole("button", { name: /2024-02-01至2024-02-29/ })).toBeInTheDocument()
  })

  it("allows custom dates and keeps empty ranges unselected", () => {
    render(<RangeFixture />)

    expect(screen.getByRole("button", { name: "上一周期" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "自定义" })).toHaveAttribute("aria-pressed", "false")
    fireEvent.click(screen.getByRole("button", { name: "自定义" }))
    expect(screen.getByRole("button", { name: "自定义" })).toHaveAttribute("aria-pressed", "true")
    fireEvent.change(screen.getByLabelText("日期范围开始日期"), { target: { value: "2026-01-03" } })
    fireEvent.change(screen.getByLabelText("日期范围结束日期"), { target: { value: "2026-01-08" } })

    expect(screen.getByRole("button", { name: /2026-01-03至2026-01-08/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "完成" }))
    expect(screen.queryByLabelText("日期范围开始日期")).not.toBeInTheDocument()
  })

  it("clips presets to the maximum date and disables the next period", () => {
    render(<RangeFixture initialStart="2026-10-01" initialEnd="2026-10-08" maxDate="2026-10-08" />)

    fireEvent.click(screen.getByRole("button", { name: "月" }))
    expect(screen.getByRole("button", { name: /2026-10-01至2026-10-08/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "月" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: "下一周期" })).toBeDisabled()

    fireEvent.click(screen.getByRole("button", { name: "上一周期" }))
    expect(screen.getByRole("button", { name: /2026-09-01至2026-09-30/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "下一周期" }))
    expect(screen.getByRole("button", { name: /2026-10-01至2026-10-08/ })).toBeInTheDocument()
  })

  it("shifts clipped weeks by calendar week", () => {
    render(<RangeFixture initialStart="2026-10-05" initialEnd="2026-10-08" maxDate="2026-10-08" />)

    fireEvent.click(screen.getByRole("button", { name: "上一周期" }))
    expect(screen.getByRole("button", { name: /2026-09-28至2026-10-04/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "下一周期" }))
    expect(screen.getByRole("button", { name: /2026-10-05至2026-10-08/ })).toBeInTheDocument()
  })

  it("defaults to today and prevents future dates in inputs and presets", () => {
    vi.setSystemTime(new Date(2026, 9, 8, 12))
    render(<RangeFixture />)

    fireEvent.click(screen.getByRole("button", { name: "自定义" }))
    const startInput = screen.getByLabelText("日期范围开始日期")
    const endInput = screen.getByLabelText("日期范围结束日期")
    expect(startInput).toHaveAttribute("max", "2026-10-08")
    expect(endInput).toHaveAttribute("max", "2026-10-08")

    fireEvent.change(startInput, { target: { value: "2026-10-09" } })
    fireEvent.change(endInput, { target: { value: "2026-10-09" } })
    expect(startInput).toHaveValue("")
    expect(endInput).toHaveValue("")

    fireEvent.click(screen.getByRole("button", { name: "月" }))
    expect(screen.getByRole("button", { name: /2026-10-01至2026-10-08/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "下一周期" })).toBeDisabled()
  })

  it("rejects a start after the end and an end before the start", () => {
    render(<RangeFixture initialStart="2026-10-01" initialEnd="2026-10-08" />)
    fireEvent.click(screen.getByRole("button", { name: "自定义" }))
    const startInput = screen.getByLabelText("日期范围开始日期")
    const endInput = screen.getByLabelText("日期范围结束日期")

    expect(startInput).toHaveAttribute("max", "2026-10-08")
    expect(endInput).toHaveAttribute("min", "2026-10-01")
    fireEvent.change(startInput, { target: { value: "2026-10-09" } })
    fireEvent.change(endInput, { target: { value: "2026-09-30" } })
    expect(startInput).toHaveValue("2026-10-01")
    expect(endInput).toHaveValue("2026-10-08")
  })
})
