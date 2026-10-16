import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"

const { mockListRecycleBin } = vi.hoisted(() => ({ mockListRecycleBin: vi.fn() }))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}))

vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/product-admin/product-table", () => ({ ProductTable: () => null }))
vi.mock("@/components/product-admin/product-detail-dialog", () => ({ ProductDetailDialog: () => null }))
vi.mock("@/components/product-admin/product-copywriting-dialog", () => ({ ProductCopywritingDialog: () => null }))
vi.mock("@/components/product-admin/product-form-dialog", () => ({ ProductFormDialog: () => null }))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: async () => ({ items: [], total: 0 }),
  listProductArchiveBrands: async () => ({ items: [] }),
  getProductYears: async () => ({ years: [] }),
  listProductRecycleBin: mockListRecycleBin,
}))

function recycleResponse(page: number, brand = "cbanner_mens") {
  return {
    items: [{
      id: page,
      brand,
      original_sku: "PRODUCT-RECYCLE-" + page,
      deleted_at: "2026-10-16T02:29:26Z",
    }],
    total: 6441,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mockListRecycleBin.mockImplementation(async ({ page, brand }) => recycleResponse(page, brand))
})

afterEach(() => cleanup())

test.each([
  ["all", "button"],
  ["all", "enter"],
  ["cbanner_mens", "button"],
  ["cbanner_mens", "enter"],
] as const)("jumps product recycle pages for %s through %s", async (brand, submitMode) => {
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  if (brand !== "all") await user.click(screen.getByRole("tab", { name: "千百度男鞋" }))
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog", { name: "商品信息档案回收站" }))
  await dialog.findByText("PRODUCT-RECYCLE-1")
  expect(mockListRecycleBin).toHaveBeenLastCalledWith({
    brand: brand === "all" ? undefined : brand, page: 1, pageSize: 20,
  })
  expect(dialog.getByText("1 / 323")).toBeInTheDocument()
  const input = dialog.getByRole("spinbutton", { name: "回收站跳转页码" })
  expect(input).toHaveAttribute("max", "323")
  const callsBeforeTyping = mockListRecycleBin.mock.calls.length
  await user.clear(input)
  await user.type(input, "24")
  expect(mockListRecycleBin).toHaveBeenCalledTimes(callsBeforeTyping)
  if (submitMode === "button") {
    await user.click(dialog.getByRole("button", { name: "跳转" }))
  } else {
    await user.keyboard("{Enter}")
  }
  await dialog.findByText("PRODUCT-RECYCLE-24")
  expect(mockListRecycleBin).toHaveBeenLastCalledWith({
    brand: brand === "all" ? undefined : brand, page: 24, pageSize: 20,
  })
  expect(dialog.getByText("24 / 323")).toBeInTheDocument()
  expect(input).toHaveValue(24)
  await user.click(dialog.getByRole("button", { name: "下一页" }))
  await dialog.findByText("PRODUCT-RECYCLE-25")
  expect(input).toHaveValue(25)
  await user.click(dialog.getByRole("button", { name: "上一页" }))
  await dialog.findByText("PRODUCT-RECYCLE-24")
  expect(input).toHaveValue(24)
  await user.clear(input)
  await user.type(input, "323{Enter}")
  await dialog.findByText("PRODUCT-RECYCLE-323")
  expect(dialog.getByRole("button", { name: "下一页" })).toBeDisabled()
  await user.click(dialog.getByRole("button", { name: "关闭商品信息档案回收站" }))
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const reopened = within(screen.getByRole("dialog", { name: "商品信息档案回收站" }))
  await reopened.findByText("PRODUCT-RECYCLE-1")
  expect(reopened.getByRole("spinbutton", { name: "回收站跳转页码" })).toHaveValue(1)
  expect(reopened.getByRole("button", { name: "上一页" })).toBeDisabled()
})

test("resets product recycle jump drafts when the brand changes", async () => {
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog", { name: "商品信息档案回收站" }))
  await dialog.findByText("PRODUCT-RECYCLE-1")
  const input = dialog.getByRole("spinbutton", { name: "回收站跳转页码" })
  await user.clear(input)
  await user.type(input, "24{Enter}")
  await dialog.findByText("PRODUCT-RECYCLE-24")
  await user.click(dialog.getByRole("button", { name: "千百度女鞋" }))
  await dialog.findByText("PRODUCT-RECYCLE-1")
  expect(mockListRecycleBin).toHaveBeenLastCalledWith({ brand: "cbanner_womens", page: 1, pageSize: 20 })
  const filteredInput = dialog.getByRole("spinbutton", { name: "回收站跳转页码" })
  expect(filteredInput).toHaveValue(1)
  await user.clear(filteredInput)
  await user.type(filteredInput, "99")
  await user.click(dialog.getByRole("button", { name: "全部品牌" }))
  await waitFor(() => expect(mockListRecycleBin).toHaveBeenLastCalledWith({ brand: undefined, page: 1, pageSize: 20 }))
  expect(dialog.getByRole("spinbutton", { name: "回收站跳转页码" })).toHaveValue(1)
})

test.each(["", "0", "-2", "324", "1.5"])("rejects invalid product recycle page %s", async (value) => {
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog", { name: "商品信息档案回收站" }))
  await dialog.findByText("PRODUCT-RECYCLE-1")
  const callsBeforeInput = mockListRecycleBin.mock.calls.length
  fireEvent.change(dialog.getByRole("spinbutton", { name: "回收站跳转页码" }), { target: { value } })
  expect(dialog.getByRole("button", { name: "跳转" })).toBeDisabled()
  fireEvent.submit(dialog.getByRole("form", { name: "回收站页码跳转" }))
  expect(mockListRecycleBin).toHaveBeenCalledTimes(callsBeforeInput)
})

test("disables product recycle jumping while loading and for an empty bin", async () => {
  let finishLoading!: (response: { items: never[]; total: number }) => void
  mockListRecycleBin.mockImplementationOnce(() => new Promise((resolve) => { finishLoading = resolve }))
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  await user.click(screen.getByRole("button", { name: "回收站" }))
  const dialog = within(screen.getByRole("dialog", { name: "商品信息档案回收站" }))
  await waitFor(() => expect(mockListRecycleBin).toHaveBeenCalledOnce())
  expect(dialog.getByRole("spinbutton", { name: "回收站跳转页码" })).toBeDisabled()
  expect(dialog.getByRole("button", { name: "跳转" })).toBeDisabled()
  await act(async () => finishLoading({ items: [], total: 0 }))
  expect(dialog.getByText("回收站暂无商品")).toBeInTheDocument()
  expect(dialog.getByRole("spinbutton", { name: "回收站跳转页码" })).toBeDisabled()
  expect(dialog.getByRole("button", { name: "跳转" })).toBeDisabled()
})
