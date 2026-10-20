import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import SuppliersPage from "@/app/suppliers/page"
import SupplierBrandsPage from "@/app/supplier-brands/page"
import { ProductAdminPage } from "@/components/product-admin/product-admin-page"

const { mockProducts, mockSuppliers, mockSupplierBrands, mockArchiveBrands, mockHasPermission } = vi.hoisted(() => ({
  mockProducts: vi.fn(), mockSuppliers: vi.fn(), mockSupplierBrands: vi.fn(), mockArchiveBrands: vi.fn(), mockHasPermission: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 1, role_code: "super_admin" }, hasPermission: mockHasPermission }),
}))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/inventory-admin/counterparty-ledger-dialog", () => ({ CounterpartyLedgerDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: mockProducts,
  listSuppliers: mockSuppliers,
  listSupplierBrands: mockSupplierBrands,
  listProductArchiveBrands: mockArchiveBrands,
  getProductYears: vi.fn().mockResolvedValue({ years: [] }),
  getProductImageRefreshStatus: vi.fn().mockResolvedValue({ in_progress: false }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mockHasPermission.mockReturnValue(true)
  window.history.replaceState(null, "", "/")
  mockProducts.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 })
  mockSuppliers.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 30 })
  mockSupplierBrands.mockResolvedValue({ items: [
    { id: 1, code: "cbanner_mens", name: "千百度男鞋" },
    { id: 2, code: "yandou", name: "烟斗" },
  ] })
  mockArchiveBrands.mockResolvedValue({ items: [] })
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

test("supplier management shows a newly created brand tab and uses its code when filtering and creating", async () => {
  const code = "supplier_brand_33aa8a0c3b6a"
  mockSupplierBrands.mockResolvedValue({ items: [{ id: 4960, code, name: "千百度赫锦" }] })
  const user = userEvent.setup()
  render(<SuppliersPage />)
  await user.click(await screen.findByRole("tab", { name: "千百度赫锦" }))
  await waitFor(() => expect(mockSuppliers).toHaveBeenLastCalledWith(expect.objectContaining({ brand: code })))
  await user.click(screen.getByRole("button", { name: "新增供应商" }))
  expect(screen.getByLabelText(/品牌/)).toHaveValue(code)
  expect(screen.getByRole("option", { name: "千百度赫锦" })).toBeInTheDocument()
})

test("brand management displays the new brand name rather than its generated code", async () => {
  const code = "supplier_brand_33aa8a0c3b6a"
  mockSupplierBrands.mockResolvedValue({ items: [{ id: 4960, code, name: "千百度赫锦" }] })
  render(<SupplierBrandsPage />)
  expect(await screen.findByRole("cell", { name: "千百度赫锦" })).toBeInTheDocument()
  expect(screen.queryByText(code)).not.toBeInTheDocument()
})

test("a new product archive brand is selectable and shows its name in product details", async () => {
  const code = "supplier_brand_33aa8a0c3b6a"
  mockArchiveBrands.mockResolvedValue({ items: [{ id: 4960, code, name: "千百度赫锦" }] })
  mockProducts.mockResolvedValue({ items: [{ id: 1, brand: code, sku: "HEJIN-001" }], total: 1, page: 1, page_size: 10 })
  mockHasPermission.mockImplementation((permission) => permission !== "product.manage")
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  await user.click(await screen.findByRole("tab", { name: "千百度赫锦" }))
  await waitFor(() => expect(mockProducts).toHaveBeenLastCalledWith(expect.objectContaining({ brand: code })))
  await user.click(await screen.findByRole("button", { name: "查看详情" }))
  const details = screen.getByRole("dialog", { name: "商品详情" })
  expect(within(details).getByText("千百度赫锦")).toBeInTheDocument()
  expect(within(details).queryByText(code)).not.toBeInTheDocument()
})

test("product archive links wait for managed brands and open the correct new brand", async () => {
  const code = "supplier_brand_33aa8a0c3b6a"
  let resolveBrands!: (value: { items: Array<{ id: number; code: string; name: string }> }) => void
  mockArchiveBrands.mockImplementation(() => new Promise((resolve) => { resolveBrands = resolve }))
  window.history.replaceState(null, "", `/products?brand=${code}&query=HEJIN-001`)
  render(<ProductAdminPage />)
  expect(mockProducts).not.toHaveBeenCalled()
  resolveBrands({ items: [{ id: 4960, code, name: "千百度赫锦" }] })
  await waitFor(() => expect(screen.getByRole("tab", { name: "千百度赫锦", selected: true })).toBeInTheDocument())
  await waitFor(() => expect(mockProducts).toHaveBeenLastCalledWith(expect.objectContaining({ brand: code, query: "HEJIN-001" })))
  expect(mockProducts.mock.calls.every(([parameters]) => parameters.brand === code)).toBe(true)
})
