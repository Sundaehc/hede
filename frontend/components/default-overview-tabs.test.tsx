import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import SuppliersPage from "@/app/suppliers/page"
import { ProductAdminPage } from "@/components/product-admin/product-admin-page"

const { mockProducts, mockSuppliers, mockSupplierBrands } = vi.hoisted(() => ({
  mockProducts: vi.fn(), mockSuppliers: vi.fn(), mockSupplierBrands: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, role_code: "super_admin" }, hasPermission: () => true }),
}))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/inventory-admin/counterparty-ledger-dialog", () => ({ CounterpartyLedgerDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: mockProducts,
  listSuppliers: mockSuppliers,
  listSupplierBrands: mockSupplierBrands,
  listProductArchiveBrands: vi.fn().mockResolvedValue({ items: [] }),
  getProductYears: vi.fn().mockResolvedValue({ years: [] }),
  getProductImageRefreshStatus: vi.fn().mockResolvedValue({ in_progress: false }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  window.history.replaceState(null, "", "/")
  mockProducts.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 })
  mockSuppliers.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 30 })
  mockSupplierBrands.mockResolvedValue({ items: [
    { id: 1, code: "cbanner_mens", name: "千百度男鞋" },
    { id: 2, code: "yandou", name: "烟斗" },
  ] })
})

afterEach(cleanup)

test("product archive starts at overview with no saved query", async () => {
  render(<ProductAdminPage />)
  expect(screen.getByRole("tab", { name: "总览", selected: true })).toBeInTheDocument()
  await waitFor(() => expect(mockProducts).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "all", page: 1 })))
})

test("product archive keeps the selected brand when returning", async () => {
  const user = userEvent.setup()
  const first = render(<ProductAdminPage />)
  await waitFor(() => expect(mockProducts).toHaveBeenCalled())
  await user.click(screen.getByRole("tab", { name: "烟斗" }))
  await waitFor(() => expect(mockProducts).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "yandou" })))
  first.unmount()
  render(<ProductAdminPage />)
  expect(screen.getByRole("tab", { name: "烟斗", selected: true })).toBeInTheDocument()
  await waitFor(() => expect(mockProducts).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "yandou" })))
})

test("supplier management starts at overview and new suppliers still get a valid brand", async () => {
  const user = userEvent.setup()
  render(<SuppliersPage />)
  await waitFor(() => expect(mockSuppliers).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "all", page: 1 })))
  expect(screen.getByRole("tab", { name: "总览", selected: true })).toBeInTheDocument()
  await screen.findByRole("tab", { name: "千百度男鞋" })
  await user.click(screen.getByRole("button", { name: "新增供应商" }))
  expect(screen.getByLabelText(/品牌/)).toHaveValue("cbanner_mens")
})

test("supplier management keeps its saved brand on return", async () => {
  const user = userEvent.setup()
  const first = render(<SuppliersPage />)
  await user.click(await screen.findByRole("tab", { name: "烟斗" }))
  await waitFor(() => expect(mockSuppliers).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "yandou" })))
  first.unmount()
  render(<SuppliersPage />)
  expect(await screen.findByRole("tab", { name: "烟斗", selected: true })).toBeInTheDocument()
  await waitFor(() => expect(mockSuppliers).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "yandou" })))
})

test("supplier management falls back to overview for a removed saved brand", async () => {
  window.sessionStorage.setItem("hede:session-query:v1:anonymous:suppliers:brand", JSON.stringify("removed-brand"))
  render(<SuppliersPage />)
  await waitFor(() => expect(screen.getByRole("tab", { name: "总览", selected: true })).toBeInTheDocument())
  await waitFor(() => expect(mockSuppliers).toHaveBeenLastCalledWith(expect.objectContaining({ brand: "all" })))
})
