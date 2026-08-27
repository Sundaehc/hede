import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ProductFormDialog } from "@/components/product-admin/product-form-dialog"
import { ApiError } from "@/lib/api"
import type { ProductListItem } from "@/lib/types"

const { mockCreateProduct, mockListProductAuxiliaryOptions, mockListProductColorBarcodes, mockListSizeGroups, mockListSuppliersByBrand, mockLookupImage, mockUpdateProduct } = vi.hoisted(() => ({
  mockCreateProduct: vi.fn(),
  mockListProductAuxiliaryOptions: vi.fn(),
  mockListProductColorBarcodes: vi.fn(),
  mockListSizeGroups: vi.fn(),
  mockListSuppliersByBrand: vi.fn(),
  mockLookupImage: vi.fn(),
  mockUpdateProduct: vi.fn(),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")

  return {
    ...actual,
    createProduct: mockCreateProduct,
    listProductAuxiliaryOptions: mockListProductAuxiliaryOptions,
    listProductColorBarcodes: mockListProductColorBarcodes,
    listSizeGroups: mockListSizeGroups,
    listSuppliersByBrand: mockListSuppliersByBrand,
    lookupImage: mockLookupImage,
    updateProduct: mockUpdateProduct,
  }
})

const NULL_FIELDS = {
  image_path: null,
  image_url: null,
  sku: null,
  original_sku: null,
  product_name: null,
  group_name: null,
  category: null,
  product_level: null,
  cost: null,
  factory_sku: null,
  color: null,
  season_category: null,
  year: null,
  upper_material: null,
  lining_material: null,
  outsole_material: null,
  insole_material: null,
  execution_standard: null,
  heel_height: null,
  shoe_width: null,
  shoe_length: null,
  shaft_circumference: null,
  shaft_height: null,
  internal_height_increase: null,
  internal_height_note: null,
  upper_height: null,
  toe_shape: null,
  closure_type: null,
  shoe_box_spec: null,
  shoe_box_type: null,
  selling_points: null,
  first_order_time: null,
  size_range: null,
  product_model: null,
  supplier_name: null,
  color_code: null,
  barcode_build_rule: null,
  launch_date: null,
}

const sampleItem: ProductListItem = {
  id: 7,
  brand: "cbanner_mens",
  image_path: "/images/original.jpg",
  image_url: "/images/serve/cbanner_mens/original.jpg",
  sku: "SKU-007",
  original_sku: "ORIG-007",
  product_name: null,
  group_name: null,
  category: null,
  product_level: null,
  cost: null,
  factory_sku: null,
  color: "黑色",
  season_category: "春季",
  year: "2026",
  upper_material: null,
  lining_material: null,
  outsole_material: null,
  insole_material: null,
  execution_standard: null,
  heel_height: null,
  shoe_width: null,
  shoe_length: null,
  shaft_circumference: null,
  shaft_height: null,
  internal_height_increase: null,
  internal_height_note: null,
  upper_height: null,
  toe_shape: null,
  closure_type: null,
  shoe_box_spec: null,
  shoe_box_type: null,
  selling_points: null,
  first_order_time: null,
  size_range: null,
  product_model: null,
  supplier_name: null,
  color_code: null,
  barcode_build_rule: null,
  launch_date: null,
  source_workbook: "book.xlsx",
  source_sheet: "sheet1",
  source_row_number: "8",
}

const nullPayload = Object.fromEntries(
  Object.entries(NULL_FIELDS).filter(([k]) => k !== "image_url").map(([k]) => [k, null]),
)

describe("ProductFormDialog", () => {
  beforeEach(() => {
    mockCreateProduct.mockReset()
    mockListProductAuxiliaryOptions.mockReset()
    mockListProductColorBarcodes.mockReset()
    mockListSizeGroups.mockReset()
    mockListSuppliersByBrand.mockReset()
    mockLookupImage.mockReset()
    mockUpdateProduct.mockReset()
    mockCreateProduct.mockResolvedValue({ item: sampleItem, message: "created" })
    mockListProductAuxiliaryOptions.mockResolvedValue({ brand: "cbanner_mens", brand_scope: "other", items: [] })
    mockListProductColorBarcodes.mockResolvedValue({ items: [] })
    mockListSizeGroups.mockResolvedValue({ items: [] })
    mockListSuppliersByBrand.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 0 })
    mockUpdateProduct.mockResolvedValue({ item: sampleItem, message: "updated" })
  })

  it("requires selecting a brand before saving in create mode", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    const onSaved = vi.fn()

    render(<ProductFormDialog open mode="create" onOpenChange={onOpenChange} onSaved={onSaved} />)

    await user.click(screen.getByRole("button", { name: "保存" }))

    expect(await screen.findByText((content, element) => element?.tagName.toLowerCase() === "p" && content === "请选择品牌")).toBeInTheDocument()
    expect(mockCreateProduct).not.toHaveBeenCalled()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it("fills image_path on successful lookup", async () => {
    const user = userEvent.setup()

    mockLookupImage.mockResolvedValue({
      found: true,
      image_path: "/images/found.jpg",
      matched_by: "original_sku",
      message: "已通过原始货号匹配图片。",
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "cbanner_mens")
    await user.type(document.getElementById("product-form-original_sku")!, "ORIG-123")
    await user.clear(document.getElementById("product-form-sku")!)
    await user.type(document.getElementById("product-form-sku")!, "SKU-123")
    await user.click(screen.getByRole("button", { name: "查询图片" }))

    await waitFor(() => {
      expect(mockLookupImage).toHaveBeenCalledWith({
        brand: "cbanner_mens",
        originalSku: "ORIG-123",
        sku: "SKU-123",
      })
    })

    expect(await screen.findByText("已匹配图片")).toBeInTheDocument()
    expect(screen.getByLabelText("图片路径")).toHaveValue("/images/found.jpg")
  })

  it("shows warning when no image exists and still allows save", async () => {
    const user = userEvent.setup()
    const onSaved = vi.fn()

    mockLookupImage.mockResolvedValue({
      found: false,
      image_path: null,
      matched_by: "none",
      message: "未找到对应图片，可继续保存商品。",
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={onSaved} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "cbanner_mens")
    await user.type(document.getElementById("product-form-original_sku")!, "ORIG-404")
    await user.click(screen.getByRole("button", { name: "查询图片" }))

    expect(await screen.findByText("未找到图片")).toBeInTheDocument()
    expect(screen.getByText("未找到对应图片，可继续保存商品。"))

    await user.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() => {
      expect(mockCreateProduct).toHaveBeenCalledWith("cbanner_mens", {
        ...nullPayload,
        original_sku: "ORIG-404",
        sku: "ORIG-404",
      })
    })

    expect(onSaved).toHaveBeenCalledTimes(1)
  })

  it("treats image lookup server errors as a non-blocking warning", async () => {
    const user = userEvent.setup()

    mockLookupImage.mockRejectedValue(new ApiError(500, "Internal Server Error"))

    render(<ProductFormDialog open mode="edit" item={sampleItem} onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.click(screen.getByRole("button", { name: "查询图片" }))

    expect(await screen.findByText("未找到图片")).toBeInTheDocument()
    expect(screen.getByText("未找到对应图片，或图片目录暂时不可用，可继续保存商品。")).toBeInTheDocument()
    expect(screen.queryByText("Internal Server Error")).not.toBeInTheDocument()
  })

  it("disables brand selection in edit mode", () => {
    render(<ProductFormDialog open mode="edit" item={sampleItem} onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    expect(screen.getByLabelText("品牌")).toBeDisabled()
    expect(screen.getByLabelText("品牌")).toHaveValue("cbanner_mens")
  })

  it("uses the original item brand when updating in edit mode", async () => {
    const user = userEvent.setup()
    const onSaved = vi.fn()

    render(<ProductFormDialog open mode="edit" item={sampleItem} onOpenChange={vi.fn()} onSaved={onSaved} />)

    await user.clear(screen.getByLabelText("颜色"))
    await user.type(screen.getByLabelText("颜色"), "白色")
    await user.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() => {
      expect(mockUpdateProduct).toHaveBeenCalledWith("cbanner_mens", 7, {
        ...nullPayload,
        image_path: "/images/original.jpg",
        sku: "SKU-007",
        original_sku: "ORIG-007",
        color: "白色",
        season_category: "春季",
        year: "2026",
      })
    })

    expect(onSaved).toHaveBeenCalledTimes(1)
  })

  it("saves the selected barcode build rule", async () => {
    const user = userEvent.setup()

    render(<ProductFormDialog open mode="edit" item={sampleItem} onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("条码构成逻辑"), "货号+颜色代码+尺码")
    await user.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() => {
      expect(mockUpdateProduct).toHaveBeenCalledWith("cbanner_mens", 7, expect.objectContaining({
        barcode_build_rule: "货号+颜色代码+尺码",
      }))
    })
  })

  it("auto-fills a unique color code after entering a color", async () => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({
      items: [{ brand: "cbanner_mens", color_code: "01", color_name: "黑色" }],
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "cbanner_mens")
    await user.type(screen.getByLabelText("颜色"), "黑色")

    await waitFor(() => {
      expect(screen.getByLabelText("颜色代码")).toHaveValue("01 - 黑色")
    })
  })

  it("auto-fills a smiley color code when the mapping has a brand suffix", async () => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({
      items: [{ brand: "smiley", color_code: "0100", color_name: "黑色（笑脸）" }],
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "smiley")
    await user.type(screen.getByLabelText("颜色"), "黑色")

    await waitFor(() => {
      expect(mockListProductColorBarcodes).toHaveBeenCalledWith("smiley")
      expect(screen.getByLabelText("颜色代码")).toHaveValue("0100 - 黑色（笑脸）")
    })
  })

  it("lists suppliers for the selected brand and saves the selected name", async () => {
    const user = userEvent.setup()
    mockListSuppliersByBrand.mockResolvedValue({
      items: [
        { id: 8, brand: "smiley", name: "笑脸测试供应商", factory_code: "XL08", contact: null, wechat: null, cooperation_status: "合作中", address: null, notes: null },
      ],
      total: 1,
      page: 1,
      page_size: 1,
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "smiley")
    await waitFor(() => expect(mockListSuppliersByBrand).toHaveBeenCalledWith("smiley"))
    await user.click(screen.getByLabelText("供应商名"))
    await user.click(await screen.findByRole("option", { name: /笑脸测试供应商/ }))

    expect(screen.getByLabelText("供应商名")).toHaveValue("笑脸测试供应商")
  })

  it("uses brand auxiliary attributes as product field options", async () => {
    const user = userEvent.setup()
    mockListProductAuxiliaryOptions.mockResolvedValue({
      brand: "cbanner_womens",
      brand_scope: "cbanner_womens",
      items: [
        { field: "product_name", type_name: "品名", options: ["女单鞋", "女靴"] },
        { field: "upper_material", type_name: "鞋面材质", options: ["合成革", "牛皮革"] },
      ],
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "cbanner_womens")
    await waitFor(() => expect(mockListProductAuxiliaryOptions).toHaveBeenCalledWith("cbanner_womens"))
    await user.click(screen.getByLabelText("品名"))
    await user.type(screen.getByLabelText("品名"), "女靴")
    await user.click(await screen.findByRole("option", { name: "女靴" }))
    await user.click(screen.getByLabelText("鞋面材质"))
    await user.type(screen.getByLabelText("鞋面材质"), "牛皮")
    await user.click(await screen.findByRole("option", { name: "牛皮革" }))

    expect(screen.getByLabelText("品名")).toHaveValue("女靴")
    expect(screen.getByLabelText("鞋面材质")).toHaveValue("牛皮革")
  })

  it("filters auxiliary dropdown options without accepting unmatched input", async () => {
    mockListProductAuxiliaryOptions.mockResolvedValue({
      brand: "cbanner_womens",
      brand_scope: "cbanner_womens",
      items: [{ field: "product_name", type_name: "品名", options: ["女单鞋"] }],
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText("品牌"), "cbanner_womens")
    await waitFor(() => expect(mockListProductAuxiliaryOptions).toHaveBeenCalledWith("cbanner_womens"))

    await user.click(screen.getByLabelText("品名"))
    await user.type(screen.getByLabelText("品名"), "不存在")

    expect(screen.getByText("没有匹配的辅助属性")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.getByLabelText("品名")).toHaveValue("")
  })
})
