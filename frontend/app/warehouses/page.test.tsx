import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import WarehousesPage from "@/app/warehouses/page"

const { brandsMock, warehousesMock, summaryMock, inventoryMock } = vi.hoisted(() => ({
  brandsMock: vi.fn(), warehousesMock: vi.fn(), summaryMock: vi.fn(), inventoryMock: vi.fn(),
}))

vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listWarehouseBrands: brandsMock,
  listWarehouses: warehousesMock,
  listWarehouseInventorySummary: summaryMock,
  getWarehouseInventory: inventoryMock,
}))

const quantities = (beginning = "10.25", ending = "14.5") => ({ items: [
  { warehouse_id: 1, beginning_qty: beginning, ending_qty: ending },
  { warehouse_id: 2, beginning_qty: "0", ending_qty: "0" },
] })

beforeEach(() => {
  vi.resetAllMocks()
  vi.useFakeTimers({ toFake: ["Date"] })
  vi.setSystemTime(new Date(2026, 10, 2, 12))
  brandsMock.mockResolvedValue({ items: [
    { id: 1, name: "甲品牌", sort_order: 0, warehouse_count: 1 },
    { id: 2, name: "乙品牌", sort_order: 1, warehouse_count: 1 },
  ] })
  warehousesMock.mockResolvedValue({ items: [
    { id: 1, brand: "甲品牌", name: "甲仓库", address: "地址甲", notes: "备注甲", sort_order: 0 },
    { id: 2, brand: "乙品牌", name: "乙仓库", address: null, notes: null, sort_order: 0 },
  ] })
  summaryMock.mockResolvedValue(quantities())
  inventoryMock.mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 20,
    totals: { beginning_qty: "10.25", inbound_qty: "4.25", outbound_qty: "0", ending_qty: "14.5" },
  })
})

afterEach(() => { cleanup(); vi.useRealTimers() })

test("shows period inventory and switches brands without another inventory request", async () => {
  const user = userEvent.setup()
  render(<WarehousesPage />)
  expect(await screen.findByText("10.25")).toBeInTheDocument()
  expect(screen.getByRole("columnheader", { name: "期初库存" })).toBeInTheDocument()
  expect(screen.getByRole("columnheader", { name: "期末库存" })).toBeInTheDocument()
  expect(screen.queryByRole("columnheader", { name: "地址" })).not.toBeInTheDocument()
  expect(screen.queryByRole("columnheader", { name: "备注" })).not.toBeInTheDocument()
  expect(summaryMock).toHaveBeenCalledOnce()
  expect(summaryMock).toHaveBeenCalledWith({ date_start: "2026-11-01", date_end: "2026-11-02" }, expect.any(AbortSignal))
  await user.click(screen.getByRole("button", { name: /^乙品牌/ }))
  const row = screen.getByRole("row", { name: /乙仓库/ })
  expect(within(row).getAllByText("0")).toHaveLength(2)
  expect(summaryMock).toHaveBeenCalledOnce()
})

test("only applies dates on query and shares the submitted dates with inventory details", async () => {
  const user = userEvent.setup()
  render(<WarehousesPage />)
  await screen.findByText("14.5")
  await user.click(screen.getByRole("button", { name: "日" }))
  expect(summaryMock).toHaveBeenCalledOnce()
  await user.click(screen.getByRole("button", { name: "查看仓库 甲仓库 库存" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({
    date_start: "2026-11-01", date_end: "2026-11-02",
  }), expect.any(AbortSignal)))
  await user.keyboard("{Escape}")
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() => expect(summaryMock).toHaveBeenLastCalledWith({ date_start: "2026-11-02", date_end: "2026-11-02" }, expect.any(AbortSignal)))
  await user.click(screen.getByRole("button", { name: "查看仓库 甲仓库 库存" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({
    date_start: "2026-11-02", date_end: "2026-11-02",
  }), expect.any(AbortSignal)))
})

test("restores submitted dates separately from draft dates and clears both", async () => {
  const user = userEvent.setup()
  const first = render(<WarehousesPage />)
  await screen.findByText("14.5")
  await user.click(screen.getByRole("button", { name: "日" }))
  first.unmount()
  render(<WarehousesPage />)
  await screen.findByText("14.5")
  expect(screen.getByRole("button", { name: "日期范围：2026-11-02至2026-11-02，点击选择日期" })).toBeInTheDocument()
  expect(summaryMock).toHaveBeenLastCalledWith({ date_start: "2026-11-01", date_end: "2026-11-02" }, expect.any(AbortSignal))
  await user.click(screen.getByRole("button", { name: "清空" }))
  await waitFor(() => expect(summaryMock).toHaveBeenLastCalledWith({ date_start: undefined, date_end: undefined }, expect.any(AbortSignal)))
  expect(screen.getByText("库存期间：最早 至 当前")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "查看仓库 甲仓库 库存" }))
  await waitFor(() => expect(inventoryMock).toHaveBeenLastCalledWith(1, expect.objectContaining({ date_start: "", date_end: "" }), expect.any(AbortSignal)))
})

test("discards a stale request after the date range changes", async () => {
  let resolveOld!: (value: ReturnType<typeof quantities>) => void
  let resolveNew!: (value: ReturnType<typeof quantities>) => void
  summaryMock.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve }))
  summaryMock.mockReturnValueOnce(new Promise((resolve) => { resolveNew = resolve }))
  const user = userEvent.setup()
  render(<WarehousesPage />)
  await screen.findByText("甲仓库")
  await user.click(screen.getByRole("button", { name: "日" }))
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(summaryMock).toHaveBeenCalledTimes(2)
  expect(summaryMock.mock.calls[0][1].aborted).toBe(true)
  await act(async () => { resolveNew(quantities("20", "30")) })
  expect(screen.getByText("30")).toBeInTheDocument()
  await act(async () => { resolveOld(quantities("900", "999")) })
  expect(screen.queryByText("999")).not.toBeInTheDocument()
  expect(screen.getByText("30")).toBeInTheDocument()
})

test("shows an error instead of outdated quantities and supports retry", async () => {
  const user = userEvent.setup()
  render(<WarehousesPage />)
  await screen.findByText("14.5")
  summaryMock.mockRejectedValueOnce(new Error("连接失败"))
  await user.click(screen.getByRole("button", { name: "日" }))
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("连接失败")
  expect(screen.queryByText("14.5")).not.toBeInTheDocument()
  expect(within(screen.getByRole("row", { name: /甲仓库/ })).getAllByText("—")).toHaveLength(2)
  await user.click(screen.getByRole("button", { name: "查询" }))
  expect(await screen.findByText("14.5")).toBeInTheDocument()
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
})
