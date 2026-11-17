import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, test } from "vitest"
import { GoodsSalesSourceStatus } from "./sales-source-status"

afterEach(cleanup)

test("shows the actual sales window and names delayed sources", () => {
  render(
    <GoodsSalesSourceStatus
      status={{
        window_start: "2026-10-17",
        window_end: "2026-11-15",
        expected_date: "2026-11-16",
        jst_latest_date: "2026-11-15",
        vip_latest_date: "2026-11-15",
        delayed_sources: ["jst", "vip"],
      }}
    />
  )
  expect(
    screen.getByText(/近30天：2026-10-17 至 2026-11-15/)
  ).toBeInTheDocument()
  expect(screen.getByRole("status")).toHaveTextContent(
    "聚水潭、唯品日销尚未更新至 2026-11-16"
  )
  expect(screen.getByText(/不能直接视为零销量/)).toBeInTheDocument()
})

test("does not report a delay once both sources reach the expected day", () => {
  render(
    <GoodsSalesSourceStatus
      status={{
        window_start: "2026-10-18",
        window_end: "2026-11-16",
        expected_date: "2026-11-16",
        jst_latest_date: "2026-11-16",
        vip_latest_date: "2026-11-16",
        delayed_sources: [],
      }}
    />
  )
  expect(screen.queryByRole("status")).not.toBeInTheDocument()
})
