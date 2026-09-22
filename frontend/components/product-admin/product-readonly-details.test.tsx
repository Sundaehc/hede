import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"
import { ProductDetailDialog } from "@/components/product-admin/product-detail-dialog"
import { ALL_PRODUCT_FIELDS } from "@/lib/fields"
import type { ProductListItem } from "@/lib/types"

const {
  mockAuth,
  mockListProducts,
  mockCreateProduct,
  mockUpdateProduct,
  mockEditOptions,
  mockPreflight,
  mockDownload,
  mockCopywriting,
} = vi.hoisted(() => ({
  mockAuth: {
    user: { role_code: "design_viewer", department_code: "美工部" },
    hasPermission: vi.fn<(permission: string) => boolean>(),
  },
  mockListProducts: vi.fn(),
  mockCreateProduct: vi.fn(),
  mockUpdateProduct: vi.fn(),
  mockEditOptions: vi.fn(),
  mockPreflight: vi.fn(),
  mockDownload: vi.fn(),
  mockCopywriting: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => mockAuth,
}))

vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listProducts: mockListProducts,
  listProductArchiveBrands: vi.fn().mockResolvedValue({ items: [] }),
  getProductYears: vi.fn().mockResolvedValue({ years: [] }),
  getProductImageRefreshStatus: vi
    .fn()
    .mockResolvedValue({ in_progress: false }),
  createProduct: mockCreateProduct,
  updateProduct: mockUpdateProduct,
  listProductAuxiliaryOptions: mockEditOptions,
  listProductColorBarcodes: mockEditOptions,
  listSizeGroupOptions: mockEditOptions,
  listSuppliersByBrand: mockEditOptions,
  lookupImage: mockEditOptions,
  assertProductExportAllowed: mockPreflight,
  downloadProductExport: mockDownload,
  getSavedProductCopywriting: mockCopywriting,
}))

const sampleItem = {
  ...Object.fromEntries(ALL_PRODUCT_FIELDS.map((field) => [field, null])),
  id: 7,
  brand: "cbanner_mens",
  image_path: "/images/read-only.jpg",
  image_url: "/images/serve/cbanner_mens/read-only.jpg",
  image_storage_path: "us3://products/cbanner_mens/read-only.jpg",
  sku: "READONLY-007",
  original_sku: "ORIGINAL-007",
  product_name: "只读测试商品",
  cost: "123.45",
  gender_costs: { female: "111.11", male: "222.22" },
  color: "黑色",
  selling_points: "完整卖点第一行\n完整卖点第二行，不应截断",
  size_range: "35-44",
  supplier_name: "测试供应商",
  source_workbook: "test.xlsx",
  source_sheet: "商品信息",
  source_row_number: "2",
} as ProductListItem

beforeEach(() => {
  vi.clearAllMocks()
  window.history.replaceState(null, "", "/products")
  mockAuth.user = { role_code: "design_viewer", department_code: "美工部" }
  mockAuth.hasPermission.mockImplementation(
    (permission) => permission === "product.view"
  )
  mockListProducts.mockResolvedValue({
    items: [sampleItem],
    total: 1,
    page: 1,
    page_size: 10,
  })
  mockEditOptions.mockResolvedValue({ brand: "cbanner_mens", items: [] })
  mockUpdateProduct.mockResolvedValue({ item: sampleItem, message: "updated" })
  mockPreflight.mockResolvedValue(undefined)
  mockDownload.mockResolvedValue({ filename: "千百度男鞋物价.xlsx", size: 100 })
  mockCopywriting.mockResolvedValue({ status: "completed", message: "", item: { content: "【主标题】\n档案生成测试文案", model: "doubao-test", generated_at: "2026-09-21T10:00:00Z", stale: false } })
})

afterEach(cleanup)

it("design users see the copywriting button immediately after details and open the correct product", async () => {
  const user = userEvent.setup()
  render(<ProductAdminPage />)
  const details = await screen.findByRole("button", { name: "查看详情" })
  const button = screen.getByRole("button", { name: "生图提示词" })
  expect(details.nextElementSibling).toBe(button)
  await user.click(button)
  expect(await screen.findByRole("dialog", { name: "生图提示词" })).toBeInTheDocument()
  expect(screen.queryByRole("dialog", { name: "商品详情" })).not.toBeInTheDocument()
  expect(mockCopywriting).toHaveBeenCalledWith("cbanner_mens", 7)
  expect(mockUpdateProduct).not.toHaveBeenCalled()
})

it.each([
  ["财务部", "finance_user", false],
  ["客服部", "customer_service_viewer", false],
  ["商品部", "product_user", false],
  ["运营部", "operation_user", false],
  ["开发部", "developer_user", false],
  ["开发部", "super_admin", true],
])("copywriting access for %s / %s is %s", async (department, role, allowed) => {
  mockAuth.user = { department_code: department, role_code: role }
  render(<ProductAdminPage />)
  await screen.findByTestId("card-title-7")
  expect(Boolean(screen.queryByRole("button", { name: "生图提示词" }))).toBe(allowed)
  expect(mockCopywriting).not.toHaveBeenCalled()
})

it.each([
  ["美工部", "design_viewer", false, "product.export"],
  ["客服部", "customer_service_viewer", false, "product.export"],
  ["商品部", "product_user", true, "product.export"],
  ["美工部", "super_admin", true, "product.export"],
  ["美工部", "design_viewer", false, "product.price_export"],
  ["客服部", "customer_service_viewer", false, "product.price_export"],
  ["财务部", "finance_user", true, "product.price_export"],
  ["美工部", "super_admin", true, "product.price_export"],
])("price export visibility for %s / %s is %s with %s", async (department, role, allowed, exportPermission) => {
  mockAuth.user = { department_code: department, role_code: role }
  mockAuth.hasPermission.mockImplementation((permission) => ["product.view", exportPermission].includes(permission))
  render(<ProductAdminPage />)
  await screen.findByTestId("card-title-7")
  if (allowed) {
    expect(screen.getByRole("button", { name: "物价导出" })).toBeInTheDocument()
  } else {
    expect(screen.queryByRole("button", { name: "物价导出" })).not.toBeInTheDocument()
  }
})

it("finance can select and export prices without product editing or general export", async () => {
  const user = userEvent.setup()
  mockAuth.user = { department_code: "财务部", role_code: "finance_user" }
  mockAuth.hasPermission.mockImplementation((permission) => ["product.view", "product.price_export"].includes(permission))
  render(<ProductAdminPage />)

  const checkbox = await screen.findByRole("checkbox", { name: "选择商品 READONLY-007" })
  await user.click(checkbox)
  expect(checkbox).toBeChecked()
  expect(screen.queryByRole("button", { name: /^(新增商品|导入 Excel|编辑|批量删除|导出 Excel|导出选中|带尺码导出)/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "物价导出" }))
  await waitFor(() => expect(mockDownload).toHaveBeenCalledWith("cbanner_mens", [7], "price", expect.any(Function), undefined, undefined, undefined, undefined, undefined))
  expect(mockPreflight).toHaveBeenCalledWith("cbanner_mens", [7], "price", undefined, undefined, undefined, undefined, undefined)
  expect(mockCreateProduct).not.toHaveBeenCalled()
  expect(mockUpdateProduct).not.toHaveBeenCalled()
})

describe("ProductDetailDialog", () => {
  it("shows full read-only values and hides costs by default", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<ProductDetailDialog item={sampleItem} onClose={onClose} />)

    const dialog = screen.getByRole("dialog", { name: "商品详情" })
    expect(within(dialog).getByText("千百度男鞋")).toBeInTheDocument()
    expect(
      within(dialog).getByText("完整卖点第一行 完整卖点第二行，不应截断")
    ).toBeInTheDocument()
    expect(within(dialog).getByText("测试供应商")).toBeInTheDocument()
    expect(
      within(dialog).getByText(sampleItem.image_storage_path!)
    ).toBeInTheDocument()
    expect(
      within(dialog).getByRole("img", { name: "READONLY-007" })
    ).toHaveAttribute("src", `/api${sampleItem.image_url}`)
    expect(dialog).not.toHaveTextContent(/成本|123\.45|111\.11|222\.22/)
    expect(
      dialog.querySelector("form, input, select, textarea, button[type=submit]")
    ).toBeNull()
    expect(
      within(dialog).queryByRole("button", { name: "保存" })
    ).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "关闭" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("shows gender costs only when explicitly permitted", () => {
    render(<ProductDetailDialog item={sampleItem} showCost onClose={vi.fn()} />)
    expect(screen.getByText("成本")).toBeInTheDocument()
    expect(screen.getByText("女码 111.11 / 男码 222.22")).toBeInTheDocument()
  })

  it("keeps long values complete and groups fields in compact sections", () => {
    const longCode = "PRODUCT-".repeat(30)
    render(
      <ProductDetailDialog
        item={{ ...sampleItem, factory_sku: longCode }}
        onClose={vi.fn()}
      />
    )

    const basicSection = screen
      .getByRole("heading", { name: "基础信息" })
      .closest("section")!
    expect(within(basicSection).getByText("工厂货号")).toBeInTheDocument()
    expect(within(basicSection).getByText(longCode)).toHaveClass(
      "[overflow-wrap:anywhere]"
    )
    const sellingPoints = screen.getByText(
      "完整卖点第一行 完整卖点第二行，不应截断"
    )
    expect(sellingPoints).toHaveClass("whitespace-pre-wrap")
    expect(sellingPoints.parentElement).toHaveClass("sm:basis-full")
    expect(
      screen.queryByText("只读查看商品资料，不可修改。")
    ).not.toBeInTheDocument()
  })

  it("uses women's field groups and displays their full values", () => {
    render(
      <ProductDetailDialog
        item={{
          ...sampleItem,
          brand: "cbanner_womens",
          upper_height: "低帮",
          sole_style: "平底",
        }}
        onClose={vi.fn()}
      />
    )
    expect(
      screen.getByRole("heading", { name: "女鞋款式信息" })
    ).toBeInTheDocument()
    expect(screen.getByText("鞋帮高度")).toBeInTheDocument()
    expect(screen.getByText("低帮")).toBeInTheDocument()
    expect(screen.getByText("平底")).toBeInTheDocument()
  })

  it("includes smiley-specific fields without leaking costs", () => {
    render(
      <ProductDetailDialog
        item={{
          ...sampleItem,
          brand: "smiley",
          factory_code: "FACTORY-007",
          market_price: 0,
          barcode: "BARCODE-007",
          accessories: "鞋带",
        }}
        onClose={vi.fn()}
      />
    )
    expect(
      screen.getByRole("heading", { name: "笑脸商品信息" })
    ).toBeInTheDocument()
    expect(screen.getByText("FACTORY-007")).toBeInTheDocument()
    expect(screen.getByText("BARCODE-007")).toBeInTheDocument()
    expect(screen.getByText("鞋带")).toBeInTheDocument()
    expect(screen.getByText("0")).toBeInTheDocument()
    expect(screen.getByRole("dialog")).not.toHaveTextContent(
      /成本|123\.45|111\.11|222\.22/
    )
  })

  it("supports managed brands, missing values and closing with Escape", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <ProductDetailDialog
        item={{ ...sampleItem, brand: "custom", image_url: null }}
        brands={[{ key: "custom", label: "自定义品牌" }]}
        onClose={onClose}
      />
    )
    expect(screen.getByText("自定义品牌")).toBeInTheDocument()
    expect(screen.getByText("暂无图片")).toBeInTheDocument()
    expect(screen.getAllByText("—").length).toBeGreaterThan(0)
    await user.keyboard("{Escape}")
    expect(onClose).toHaveBeenCalledOnce()
  })
})

describe("ProductAdminPage read-only access", () => {
  it.each([
    ["财务部", "finance_user", true],
    ["美工部", "design_viewer", false],
    ["客服部", "customer_service_viewer", false],
  ])(
    "lets %s open read-only cards with the appropriate cost visibility",
    async (department, role, canViewCost) => {
      const user = userEvent.setup()
      mockAuth.user = { department_code: department, role_code: role }
      render(<ProductAdminPage />)

      const card = await screen.findByRole("button", {
        name: "查看商品详情 READONLY-007",
      })
      if (canViewCost) {
        expect(card).toHaveTextContent("女码 111.11 / 男码 222.22")
      } else {
        expect(card).not.toHaveTextContent(/成本|123\.45|111\.11|222\.22/)
      }
      expect(
        screen.queryByRole("button", { name: "新增商品" })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole("button", { name: "导入 Excel" })
      ).not.toBeInTheDocument()
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()

      await user.click(card)
      const dialog = screen.getByRole("dialog", { name: "商品详情" })
      expect(
        within(dialog).queryByText("只读查看商品资料，不可修改。")
      ).not.toBeInTheDocument()
      expect(
        within(dialog).getByText("只读测试商品", { selector: "dd" })
      ).toBeInTheDocument()
      if (canViewCost) {
        expect(within(dialog).getByText("成本")).toBeInTheDocument()
        expect(
          within(dialog).getByText("女码 111.11 / 男码 222.22")
        ).toBeInTheDocument()
      } else {
        expect(dialog).not.toHaveTextContent(/成本|123\.45|111\.11|222\.22/)
      }
      expect(dialog.querySelector("input, textarea, select, form")).toBeNull()
      expect(
        screen.queryByRole("button", { name: "保存" })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole("button", { name: "编辑" })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole("button", { name: "删除" })
      ).not.toBeInTheDocument()

      await user.keyboard("{Enter}")
      expect(mockCreateProduct).not.toHaveBeenCalled()
      expect(mockUpdateProduct).not.toHaveBeenCalled()
      expect(mockEditOptions).not.toHaveBeenCalled()
    }
  )

  it.each(["{Enter}", " "])(
    "opens read-only cards with the %s key",
    async (key) => {
      const user = userEvent.setup()
      render(<ProductAdminPage />)
      const card = await screen.findByRole("button", {
        name: "查看商品详情 READONLY-007",
      })
      card.focus()
      await user.keyboard(key)
      expect(
        screen.getByRole("dialog", { name: "商品详情" })
      ).toBeInTheDocument()
    }
  )

  it("opens read-only details from the overview with the item's own brand", async () => {
    const user = userEvent.setup()
    render(<ProductAdminPage />)
    await screen.findByTestId("card-title-7")
    await user.click(screen.getByRole("tab", { name: "总览" }))
    await user.click(await screen.findByRole("button", { name: "查看详情" }))
    const dialog = screen.getByRole("dialog", { name: "商品详情" })
    expect(within(dialog).getByText("千百度男鞋")).toBeInTheDocument()
    expect(within(dialog).queryByText("总览")).not.toBeInTheDocument()
  })

  it("keeps copying codes and image preview separate from opening details", async () => {
    const user = userEvent.setup()
    render(<ProductAdminPage />)
    await user.click(
      await screen.findByRole("button", { name: "复制货号 READONLY-007" })
    )
    expect(
      screen.queryByRole("dialog", { name: "商品详情" })
    ).not.toBeInTheDocument()
    await user.click(
      screen.getByRole("button", { name: "查看原图 READONLY-007" })
    )
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(
      screen.queryByRole("dialog", { name: "商品详情" })
    ).not.toBeInTheDocument()
  })

  it("does not expose a detail action without product viewing permission", async () => {
    mockAuth.hasPermission.mockReturnValue(false)
    render(<ProductAdminPage />)
    await screen.findByTestId("card-title-7")
    expect(
      screen.queryByRole("button", { name: /查看商品详情|查看详情/ })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("dialog", { name: "商品详情" })
    ).not.toBeInTheDocument()
  })

  it.each([
    ["商品部", "product_user"],
    ["运营部", "operation_user"],
    ["开发部", "developer_user"],
    ...["财务部", "商品部", "运营部", "开发部", "美工部", "客服部"].map(
      (department) => [department, "super_admin"]
    ),
  ])(
    "preserves editing and cost visibility for %s / %s",
    async (department, role) => {
      const user = userEvent.setup()
      mockAuth.user = { department_code: department, role_code: role }
      const permissions =
        role === "super_admin"
          ? ["*"]
          : [
              "product.view",
              "product.manage",
              "product.import",
              "product.export",
            ]
      mockAuth.hasPermission.mockImplementation(
        (permission) =>
          permissions.includes("*") || permissions.includes(permission)
      )
      render(<ProductAdminPage />)

      const card = await screen.findByRole("button", {
        name: "编辑商品 READONLY-007",
      })
      expect(card).toHaveTextContent("女码 111.11 / 男码 222.22")
      expect(
        screen.getByRole("button", { name: "新增商品" })
      ).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "编辑" })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: "删除" })).toBeInTheDocument()
      await user.click(card)
      const dialog = screen.getByRole("dialog", { name: "编辑商品" })
      expect(within(dialog).getByLabelText("品牌")).toBeDisabled()
      expect(within(dialog).getByLabelText("成本")).toHaveValue("123.45")
      await user.clear(within(dialog).getByLabelText("颜色"))
      await user.type(within(dialog).getByLabelText("颜色"), "白色")
      await user.click(within(dialog).getByRole("button", { name: "保存" }))

      expect(mockUpdateProduct).toHaveBeenCalledWith(
        "cbanner_mens",
        7,
        expect.objectContaining({ color: "白色" })
      )
      expect(mockCreateProduct).not.toHaveBeenCalled()
    }
  )
})
