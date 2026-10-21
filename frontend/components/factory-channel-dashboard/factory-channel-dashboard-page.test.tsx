import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { FactoryChannelDashboardPage } from "@/components/factory-channel-dashboard/factory-channel-dashboard-page"
import { clearSessionQueryStates } from "@/lib/session-query-state"
import type { FactoryChannelDashboardResponse } from "@/lib/types"

const { dashboardMock } = vi.hoisted(() => ({ dashboardMock: vi.fn() }))

vi.mock("@/lib/api", () => ({ getFactoryChannelDashboard: dashboardMock }))

function dashboardResponse(year = 2026, factoryName = "测试工厂"): FactoryChannelDashboardResponse {
  const totals = {
    style_count: 1,
    total_sales: 10,
    total_net_sales: 8,
    total_returns: 2,
    traditional_sales: 10,
    traditional_net_sales: 8,
    traditional_returns: 2,
    live_sales: 0,
    live_net_sales: 0,
    live_returns: 0,
    clearance_sales: 0,
    clearance_net_sales: 0,
    clearance_returns: 0,
  }
  return {
    brand: "cbanner_mens",
    sales_year: year,
    product_year: null,
    date_start: null,
    date_end: null,
    latest_sales_date: `${year}-01-01`,
    available_sales_years: [2024, 2025, 2026],
    available_product_years: ["2025", "2026"],
    sales_date_coverage: {
      expected_start: null,
      expected_end: null,
      missing_date_count: 0,
      missing_dates: [],
      pending_refresh_date_count: 0,
      pending_refresh_dates: [],
      sources: [],
    },
    summary: {
      ...totals,
      factory_count: 1,
      unmatched_sales: 0,
      unclassified_style_count: 0,
      unclassified_sales: 0,
    },
    seasons: [{
      key: "spring_summer",
      label: "春夏款",
      items: [{
        ...totals,
        factory_name: factoryName,
        factory_code: "F001",
        traditional_ratio: 100,
        live_ratio: 0,
        clearance_ratio: 0,
      }],
    }],
  }
}

function deferredResponse() {
  let resolve!: (value: FactoryChannelDashboardResponse) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<FactoryChannelDashboardResponse>((onResolve, onReject) => {
    resolve = onResolve
    reject = onReject
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.resetAllMocks()
  window.sessionStorage.clear()
  clearSessionQueryStates()
  window.history.replaceState({}, "", "/factory-channel-dashboard")
  dashboardMock.mockResolvedValue(dashboardResponse())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function openDashboard() {
  const rendered = render(<FactoryChannelDashboardPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled())
  return rendered
}

test("selects and persists the automatic year without querying twice", async () => {
  const rendered = await openDashboard()
  expect(screen.getByRole("combobox", { name: "销售年份" })).toHaveValue("2026")
  expect(dashboardMock).toHaveBeenCalledOnce()
  expect(dashboardMock).toHaveBeenCalledWith(
    expect.objectContaining({ brand: "cbanner_mens", salesYear: undefined, cacheBust: undefined }),
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  )
  rendered.unmount()
  await openDashboard()
  expect(dashboardMock).toHaveBeenCalledTimes(2)
  expect(dashboardMock.mock.calls[1][0].salesYear).toBe(2026)
})

test("loads route filters directly without sending the default brand query", async () => {
  window.history.replaceState({}, "", "/factory-channel-dashboard?brand=cbanner_womens&sales_year=2025")
  dashboardMock.mockResolvedValue(dashboardResponse(2025))
  await openDashboard()
  expect(dashboardMock).toHaveBeenCalledOnce()
  expect(dashboardMock.mock.calls[0][0]).toMatchObject({ brand: "cbanner_womens", salesYear: 2025 })
})

test("cancels superseded queries and ignores a late success", async () => {
  await openDashboard()
  const older = deferredResponse()
  const latest = deferredResponse()
  dashboardMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
  fireEvent.change(screen.getByRole("combobox", { name: "销售年份" }), { target: { value: "2025" } })
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledTimes(2))
  const olderSignal = dashboardMock.mock.calls[1][1].signal as AbortSignal
  fireEvent.change(screen.getByRole("combobox", { name: "销售年份" }), { target: { value: "2024" } })
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledTimes(3))
  expect(olderSignal.aborted).toBe(true)
  await act(async () => latest.resolve(dashboardResponse(2024, "最新工厂")))
  expect(screen.getByText("最新工厂")).toBeInTheDocument()
  await act(async () => older.resolve(dashboardResponse(2025, "过期工厂")))
  expect(screen.queryByText("过期工厂")).not.toBeInTheDocument()
  expect(screen.getByText("最新工厂")).toBeInTheDocument()
  expect(screen.getByRole("combobox", { name: "销售年份" })).toHaveValue("2024")
})

test("a late error does not clear the newest query loading state", async () => {
  await openDashboard()
  const older = deferredResponse()
  const latest = deferredResponse()
  dashboardMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
  fireEvent.change(screen.getByRole("combobox", { name: "品牌" }), { target: { value: "cbanner_womens" } })
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledTimes(2))
  fireEvent.change(screen.getByRole("combobox", { name: "品牌" }), { target: { value: "cbanner_mens" } })
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledTimes(3))
  await act(async () => older.reject(new Error("过期请求失败")))
  expect(screen.queryByText("过期请求失败")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "刷新" })).toBeDisabled()
  await act(async () => latest.resolve(dashboardResponse()))
  expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
})

test("unmount aborts an in-flight query", async () => {
  const pending = deferredResponse()
  dashboardMock.mockReturnValue(pending.promise)
  const rendered = render(<FactoryChannelDashboardPage />)
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledOnce())
  const signal = dashboardMock.mock.calls[0][1].signal as AbortSignal
  rendered.unmount()
  expect(signal.aborted).toBe(true)
  await act(async () => pending.resolve(dashboardResponse()))
})

test("factory search stays local and refresh bypasses cache only once", async () => {
  const user = userEvent.setup()
  await openDashboard()
  await user.type(screen.getByPlaceholderText("名称或工厂代码"), "没有的工厂")
  expect(screen.queryByText("测试工厂")).not.toBeInTheDocument()
  expect(dashboardMock).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledTimes(2))
  expect(dashboardMock.mock.calls[1][0]).toMatchObject({ salesYear: 2026, cacheBust: "1" })
  await user.selectOptions(screen.getByRole("combobox", { name: "品牌" }), "cbanner_womens")
  await waitFor(() => expect(dashboardMock).toHaveBeenCalledTimes(3))
  expect(dashboardMock.mock.calls[2][0].cacheBust).toBeUndefined()
})

test("reset resolves the latest year once again without a duplicate query", async () => {
  const user = userEvent.setup()
  await openDashboard()
  dashboardMock.mockResolvedValueOnce(dashboardResponse(2025))
  await user.selectOptions(screen.getByRole("combobox", { name: "销售年份" }), "2025")
  await waitFor(() => expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled())
  await user.click(screen.getByRole("button", { name: "重置" }))
  await waitFor(() => expect(screen.getByRole("combobox", { name: "销售年份" })).toHaveValue("2026"))
  expect(dashboardMock).toHaveBeenCalledTimes(3)
  expect(dashboardMock.mock.calls[2][0].salesYear).toBeUndefined()
})

test("the active request failure is shown and can be retried", async () => {
  dashboardMock.mockRejectedValueOnce(new Error("数据查询失败"))
  await openDashboard()
  expect(screen.getByText("数据查询失败")).toBeInTheDocument()
  await userEvent.click(screen.getByRole("button", { name: "刷新" }))
  await waitFor(() => expect(screen.getByText("测试工厂")).toBeInTheDocument())
  expect(screen.queryByText("数据查询失败")).not.toBeInTheDocument()
  expect(dashboardMock).toHaveBeenCalledTimes(2)
})
