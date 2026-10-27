import { render, screen, waitFor, within } from "@testing-library/react"
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
    listSizeGroupOptions: mockListSizeGroups,
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
  cost_price: null,
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

  it("keeps the original amount as factory shipping price and saves cost price independently", async () => {
    const user = userEvent.setup()
    render(<ProductFormDialog open mode="edit" item={{ ...sampleItem, cost: "118", cost_price: null }} onOpenChange={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByText("物价信息")).toBeInTheDocument()
    expect(screen.getByLabelText("工厂出货价")).toHaveValue("118")
    expect(screen.getByLabelText("成本价")).toHaveValue("")
    await user.type(screen.getByLabelText("成本价"), "136.50")
    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockUpdateProduct).toHaveBeenCalledWith("cbanner_mens", 7, expect.objectContaining({ cost: "118", cost_price: "136.50" })))
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

    await user.click(screen.getByLabelText("条码构成逻辑"))
    await user.click(screen.getByRole("option", { name: "货号+颜色代码+尺码" }))
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

  it("uses a compact searchable size selector in the product editor and saves its name", async () => {
    const user = userEvent.setup()
    mockListSizeGroups.mockResolvedValue({ items: [
      { id: 1, name: "女鞋尺码组220-250", product_count: 0, items: [{ id: 1, size_name: "220", barcode: "220", sort_order: 0 }] },
      { id: 2, name: "男鞋尺码组240-270", product_count: 0, items: [{ id: 2, size_name: "240", barcode: "240", sort_order: 0 }] },
    ] })
    render(<ProductFormDialog open mode="edit" item={{ ...sampleItem, size_range: "男鞋尺码组240-270" }} onOpenChange={vi.fn()} onSaved={vi.fn()} />)
    const trigger = screen.getByLabelText("尺码段")
    await waitFor(() => expect(trigger).toBeEnabled())
    expect(trigger.tagName).toBe("BUTTON")
    await user.click(trigger)
    const panel = screen.getByRole("dialog", { name: "选择尺码段" })
    expect(panel.closest('[data-slot="dialog-content"]')).toBe(screen.getByRole("dialog", { name: "编辑商品" }))
    expect(within(panel).getByRole("option", { name: "男鞋尺码组240-270 1 码" })).toHaveAttribute("aria-selected", "true")
    await user.type(screen.getByRole("combobox", { name: "搜索尺码段" }), "220")
    await user.click(screen.getByRole("option", { name: "女鞋尺码组220-250 1 码" }))
    expect(trigger).toHaveTextContent("女鞋尺码组220-250")
    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockUpdateProduct).toHaveBeenCalledWith("cbanner_mens", 7, expect.objectContaining({ size_range: "女鞋尺码组220-250" })))
  })

  it("keeps saved size names and season unchanged when dismissing dropdowns", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<ProductFormDialog open mode="edit" item={{ ...sampleItem, size_range: "历史尺码组" }} onOpenChange={onOpenChange} onSaved={vi.fn()} />)
    const trigger = screen.getByLabelText("尺码段")
    await waitFor(() => expect(trigger).toBeEnabled())
    await user.click(trigger)
    await user.keyboard("{Escape}")
    expect(trigger).toHaveTextContent("历史尺码组")
    await user.click(screen.getByLabelText("季节分类"))
    await user.click(screen.getByRole("option", { name: "冬季" }))
    expect(screen.getByLabelText("季节分类")).toHaveValue("冬季")
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it.each([null, "NS-MANUAL"])("does not match NS color codes when editing with saved code %s", async (colorCode) => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({ items: [{ brand: "ns", color_code: "01", color_name: "黑色" }] })
    render(<ProductFormDialog open mode="edit" brands={[{ key: "ns", label: "NS" }]} item={{ ...sampleItem, brand: "ns", color: "黑色", color_code: colorCode }} onOpenChange={vi.fn()} onSaved={vi.fn()} />)
    const input = screen.getByLabelText("颜色代码")
    expect(input).toHaveAttribute("type", "text")
    expect(input).not.toHaveAttribute("role", "combobox")
    expect(input).toHaveValue(colorCode ?? "")
    await user.clear(screen.getByLabelText("颜色"))
    await user.type(screen.getByLabelText("颜色"), "白色")
    expect(input).toHaveValue(colorCode ?? "")
    expect(mockListProductColorBarcodes).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockUpdateProduct).toHaveBeenCalledWith("ns", 7, expect.objectContaining({ color: "白色", color_code: colorCode })))
  })

  it("accepts an arbitrary manually entered NS color code without matching options", async () => {
    const user = userEvent.setup()
    render(<ProductFormDialog open mode="create" brands={[{ key: "ns", label: "NS" }]} onOpenChange={vi.fn()} onSaved={vi.fn()} />)
    await user.selectOptions(screen.getByLabelText("品牌"), "ns")
    await user.type(screen.getByLabelText("商品货号"), "NS-001")
    await user.type(screen.getByLabelText("颜色"), "黑色")
    expect(screen.getByLabelText("颜色代码")).toHaveValue("")
    await user.type(screen.getByLabelText("颜色代码"), "001-CUSTOM")
    expect(screen.getByLabelText("颜色")).toHaveValue("黑色")
    expect(mockListProductColorBarcodes).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledWith("ns", expect.objectContaining({ color: "黑色", color_code: "001-CUSTOM" })))
  })

  it("clears an automatically matched code when switching to NS without matching again", async () => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({ items: [{ brand: "cbanner_mens", color_code: "01", color_name: "黑色" }] })
    render(<ProductFormDialog open mode="create" brands={[{ key: "cbanner_mens", label: "千百度男鞋" }, { key: "ns", label: "NS" }]} onOpenChange={vi.fn()} onSaved={vi.fn()} />)
    await user.selectOptions(screen.getByLabelText("品牌"), "cbanner_mens")
    await user.type(screen.getByLabelText("颜色"), "黑色")
    await waitFor(() => expect(screen.getByLabelText("颜色代码")).toHaveValue("01 - 黑色"))
    await user.selectOptions(screen.getByLabelText("品牌"), "ns")
    expect(screen.getByLabelText("颜色代码")).toHaveValue("")
    await user.type(screen.getByLabelText("颜色"), "色")
    expect(screen.getByLabelText("颜色代码")).toHaveValue("")
    expect(mockListProductColorBarcodes).not.toHaveBeenCalledWith("ns")
  })

  it("uses the last four characters of the smiley SKU instead of the color mapping", async () => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({
      items: [{ brand: "smiley", color_code: "0100", color_name: "黑色（笑脸）" }],
    })

    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "smiley")
    await user.type(screen.getByLabelText("商品货号"), "6362022365400")
    await user.type(screen.getByLabelText("颜色"), "黑色")

    await waitFor(() => {
      expect(mockListProductColorBarcodes).toHaveBeenCalledWith("smiley")
      expect(screen.getByLabelText("颜色代码")).toHaveValue("5400")
    })
    expect(screen.getByLabelText("颜色代码")).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledWith("smiley", expect.objectContaining({
      sku: "6362022365400",
      color_code: "5400",
    })))
  })

  it("corrects an existing smiley product color code when editing", async () => {
    const user = userEvent.setup()
    const item = { ...sampleItem, brand: "smiley" as const, sku: "6362022365400", color_code: "6362022365400" }

    render(<ProductFormDialog open mode="edit" item={item} onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    expect(screen.getByLabelText("颜色代码")).toHaveValue("5400")
    await user.clear(screen.getByLabelText("商品货号"))
    await user.type(screen.getByLabelText("商品货号"), "6362022361234")
    expect(screen.getByLabelText("颜色代码")).toHaveValue("1234")

    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockUpdateProduct).toHaveBeenCalledWith("smiley", 7, expect.objectContaining({
      sku: "6362022361234",
      color_code: "1234",
    })))
  })

  it("searches smiley codes and fills the selected color", async () => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({
      items: [
        { brand: "smiley", color_code: "5400", color_name: "棕色（笑脸）" },
        { brand: "smiley", color_code: "0100", color_name: "黑色（笑脸）" },
      ],
    })
    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "smiley")
    await user.type(screen.getByLabelText("商品货号"), "6362022365400")
    await waitFor(() => expect(screen.getByLabelText("颜色")).toHaveValue("棕色（笑脸）"))
    expect(screen.getByLabelText("颜色代码")).toHaveValue("5400 - 棕色（笑脸）")
    await user.click(screen.getByLabelText("颜色代码"))
    await user.type(screen.getByLabelText("颜色代码"), "黑色")
    await user.click(await screen.findByRole("option", { name: /0100.*黑色（笑脸）/ }))
    await waitFor(() => expect(screen.getByLabelText("颜色")).toHaveValue("黑色（笑脸）"))
    await user.type(screen.getByLabelText("商品货号"), "9")
    expect(screen.getByLabelText("颜色代码")).toHaveValue("0100 - 黑色（笑脸）")

    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledWith("smiley", expect.objectContaining({
      sku: "63620223654009",
      color_code: "0100",
      color: "黑色（笑脸）",
    })))
  })

  it("accepts a custom smiley code when no option matches", async () => {
    const user = userEvent.setup()
    mockListProductColorBarcodes.mockResolvedValue({ items: [] })
    render(<ProductFormDialog open mode="create" onOpenChange={vi.fn()} onSaved={vi.fn()} />)

    await user.selectOptions(screen.getByLabelText("品牌"), "smiley")
    await user.type(screen.getByLabelText("商品货号"), "6362022365400")
    await user.click(screen.getByLabelText("颜色代码"))
    await user.type(screen.getByLabelText("颜色代码"), "0100")
    expect(screen.getByText("没有匹配的颜色代码")).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.getByLabelText("颜色代码")).toHaveValue("0100")

    await user.click(screen.getByRole("button", { name: "保存" }))
    await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledWith("smiley", expect.objectContaining({
      color_code: "0100",
    })))
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

  it.each(["create", "edit"] as const)("supports Hejin women's style fields when %s", async (mode) => {
    const user = userEvent.setup()
    const brand = "supplier_brand_33aa8a0c3b6a"
    const fields = [
      ["sole_style", "跟底款式", "厚底"],
      ["fashion_elements", "流行元素", "蝴蝶结"],
      ["upper_height", "鞋帮高度", "低帮"],
      ["opening_depth", "开口深度", "浅口"],
      ["boot_shaft", "靴筒", "短筒"],
      ["closure_type", "闭合方式", "搭扣"],
      ["mesh_upper_type", "鞋网面类型", "网面"],
      ["toe_shape", "鞋头款式", "方头"],
      ["rear_heel_height", "后跟高", "5cm"],
    ]
    render(<ProductFormDialog open mode={mode} item={mode === "edit" ? { ...sampleItem, brand } : undefined} brands={[{ key: brand, label: "千百度赫锦" }]} onOpenChange={vi.fn()} onSaved={vi.fn()} />)
    if (mode === "create") {
      await user.selectOptions(screen.getByLabelText("品牌"), brand)
      await user.type(screen.getByLabelText("商品货号"), "HJ-001")
    }
    await waitFor(() => expect(mockListProductAuxiliaryOptions).toHaveBeenCalledWith(brand))
    expect(screen.getByText("女鞋款式信息")).toBeInTheDocument()
    for (const [, label, value] of fields) {
      await user.type(screen.getByLabelText(label), value)
    }
    await user.click(screen.getByRole("button", { name: "保存" }))
    const expected = expect.objectContaining(Object.fromEntries(fields.map(([field, , value]) => [field, value])))
    if (mode === "edit") {
      await waitFor(() => expect(mockUpdateProduct).toHaveBeenCalledWith(brand, 7, expected))
    } else {
      await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledWith(brand, expected))
    }
  })
})
