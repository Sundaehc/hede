import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"
import { ProductAdminPage } from "@/components/product-admin/product-admin-page"

const { list, importFile } = vi.hoisted(() => ({ list: vi.fn(), importFile: vi.fn() }))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ hasPermission: () => true }),
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: list,
  importProducts: importFile,
  listProductArchiveBrands: async () => ({ items: [] }),
  getProductSearchOptions: async () => ({ years: [], seasons: [], product_names: [] }),
  getProductImageRefreshStatus: async () => ({ in_progress: false }),
}))
vi.mock("@/components/product-admin/product-table", () => ({
  ProductTable: ({ items }: { items: { id: number; sku: string }[] }) => <div>{items.map((item) => <span key={item.id}>{item.sku}</span>)}</div>,
}))
afterEach(() => { cleanup(); vi.clearAllMocks() })

test("shows imported products in their original brand after switching brands during upload", async () => {
  const prefix = "hede:session-query:v1:anonymous:products:"
  for (const [key, value] of Object.entries({ brand: "cbanner_womens", page: 3, year: "2020", season: "冬季", productName: "旧品名", supplierName: "旧供应商", supplierNameInput: "旧草稿", supplierNameValues: ["旧供应商"], submittedSkuPrefix: "OLD" })) {
    window.sessionStorage.setItem(prefix + key, JSON.stringify(value))
  }
  let imported = false
  let resolveImport!: (value: object) => void
  let resolveOldList!: (value: object) => void
  list.mockImplementation(async (params) => {
    if (params.brand === "cbanner_mens") return new Promise((resolve) => { resolveOldList = resolve })
    const show = imported && params.brand === "cbanner_womens" && params.query === "NEW-SKU" && params.page === 1
      && !params.year && !params.season && !params.productName && !params.supplierName && !params.skuPrefix
    return { items: show ? [{ id: 9, sku: "NEW-SKU", brand: "cbanner_womens" }] : [], total: show ? 1 : 0 }
  })
  importFile.mockImplementationOnce(() => new Promise((resolve) => { resolveImport = resolve }))
  const user = userEvent.setup()
  const view = render(<ProductAdminPage />)
  await waitFor(() => expect(list).toHaveBeenCalledWith(expect.objectContaining({ brand: "cbanner_womens", page: 3 })))
  const input = view.container.querySelector<HTMLInputElement>('input[type="file"]')!
  fireEvent.change(input, { target: { files: [new File(["excel"], "商品.xlsx")] } })
  await waitFor(() => expect(importFile).toHaveBeenCalledOnce())
  await user.click(screen.getByRole("tab", { name: "千百度男鞋" }))
  await waitFor(() => expect(resolveOldList).toBeTypeOf("function"))
  imported = true
  await act(async () => resolveImport({ skus: ["NEW-SKU"], message: "新增 1 条" }))
  expect(await screen.findByText("NEW-SKU", { selector: "span" })).toBeInTheDocument()
  await user.click(within(screen.getByRole("alertdialog", { name: "导入完成" })).getByRole("button", { name: "确定" }))
  expect(screen.getByRole("tab", { name: "千百度女鞋", selected: true })).toBeInTheDocument()
  await act(async () => resolveOldList({ items: [{ id: 1, sku: "STALE-SKU" }], total: 1 }))
  expect(screen.queryByText("STALE-SKU")).not.toBeInTheDocument()
  expect(screen.getByText("NEW-SKU", { selector: "span" })).toBeInTheDocument()
  // Reimporting the same SKU must query again even though search terms are unchanged.
  const previousLoads = list.mock.calls.length
  importFile.mockResolvedValueOnce({ skus: ["NEW-SKU"], message: "更新 1 条" })
  fireEvent.change(input, { target: { files: [new File(["excel"], "商品.xlsx")] } })
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(previousLoads))
})
