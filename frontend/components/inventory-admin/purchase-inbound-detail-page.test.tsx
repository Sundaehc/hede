import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { PurchaseInboundDetailPage } from "@/components/inventory-admin/purchase-inbound-detail-page"

const { listMock, brandsMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  brandsMock: vi.fn(),
}))

vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listPurchaseInboundDetails: listMock,
  listInventoryBrands: brandsMock,
  listSuppliers: async () => ({ items: [] }),
  listWarehouses: async () => ({ items: [] }),
  listInventoryDetailCandidates: async () => ({ items: [] }),
}))

let downloads: string[] = []

beforeEach(() => {
  vi.resetAllMocks()
  window.localStorage.clear()
  window.sessionStorage.clear()
  brandsMock.mockResolvedValue({
    items: [
      { value: "cbanner_mens", label: "千百度男鞋" },
      { value: "yandou", label: "烟斗" },
      { value: "custom", label: "自定义品牌" },
    ],
  })
  const totals = {
    purchase_quantity: "0",
    purchase_amount: "0",
    retail_amount: "",
  }
  listMock.mockResolvedValue({
    items: [],
    total: 101,
    totals: { ...totals, current_page: totals, all: totals },
  })
  downloads = []
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement
  ) {
    downloads.push(this.href)
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

async function openPage() {
  const user = userEvent.setup()
  const rendered = render(<PurchaseInboundDetailPage />)
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "查询" })).toBeEnabled()
  )
  return { user, ...rendered }
}

test("supports the same searchable brand multiselect as inventory without querying before submission", async () => {
  const { user } = await openPage()
  expect(brandsMock).toHaveBeenCalledOnce()
  const calls = listMock.mock.calls.length
  const brandInput = screen.getByRole("combobox", { name: "品牌" })
  await user.type(brandInput, "千百度")
  await user.click(await screen.findByRole("button", { name: "千百度男鞋" }))
  await user.click(await screen.findByRole("button", { name: "烟斗" }))
  expect(listMock).toHaveBeenCalledTimes(calls)
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ brands: ["cbanner_mens", "yandou"], page: 1 })
    )
  )
  await user.click(screen.getByLabelText("Go to next page"))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ brands: ["cbanner_mens", "yandou"], page: 2 })
    )
  )
})

test("exports applied brand filters rather than an unsubmitted brand draft", async () => {
  const { user } = await openPage()
  await user.click(screen.getByRole("combobox", { name: "品牌" }))
  await user.click(await screen.findByRole("button", { name: "烟斗" }))
  await user.click(screen.getByRole("button", { name: "查询" }))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ brands: ["yandou"] })
    )
  )
  await user.click(screen.getByRole("combobox", { name: "品牌" }))
  await user.click(await screen.findByRole("button", { name: "自定义品牌" }))
  await user.click(screen.getByRole("button", { name: "导出Excel" }))
  expect(new URL(downloads[0]).searchParams.getAll("brands")).toEqual([
    "yandou",
  ])
  expect(new URL(downloads[0]).searchParams.has("page")).toBe(false)
  await user.click(screen.getByRole("button", { name: "清空" }))
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith({ page: 1, pageSize: 50 })
  )
  expect(
    screen.queryByRole("button", { name: "移除 烟斗" })
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole("button", { name: "移除 自定义品牌" })
  ).not.toBeInTheDocument()
})

test("submits selected brands with Enter and restores the selection after returning", async () => {
  const { user, unmount } = await openPage()
  const input = screen.getByRole("combobox", { name: "品牌" })
  await user.type(input, "自定义")
  await user.keyboard("{Enter}")
  await user.keyboard("{Enter}")
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ brands: ["custom"] })
    )
  )
  unmount()
  render(<PurchaseInboundDetailPage />)
  expect(
    await screen.findByRole("button", { name: "移除 自定义品牌" })
  ).toBeInTheDocument()
  await waitFor(() =>
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ brands: ["custom"] })
    )
  )
})
