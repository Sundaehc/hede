import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ProductFormDialog } from "@/components/product-admin/product-form-dialog"
import { ApiError } from "@/lib/api"
import type { ProductListItem } from "@/lib/types"

const { mockCreateProduct, mockLookupImage, mockUpdateProduct } = vi.hoisted(() => ({
  mockCreateProduct: vi.fn(),
  mockLookupImage: vi.fn(),
  mockUpdateProduct: vi.fn(),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")

  return {
    ...actual,
    createProduct: mockCreateProduct,
    lookupImage: mockLookupImage,
    updateProduct: mockUpdateProduct,
  }
})

const NULL_FIELDS = {
  image_path: null,
  image_url: null,
  sku: null,
  original_sku: null,
  group_name: null,
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
  launch_date: null,
}

const sampleItem: ProductListItem = {
  id: 7,
  brand: "cbanner_mens",
  image_path: "/images/original.jpg",
  image_url: "/images/serve/cbanner_mens/original.jpg",
  sku: "SKU-007",
  original_sku: "ORIG-007",
  group_name: null,
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
    mockLookupImage.mockReset()
    mockUpdateProduct.mockReset()
    mockCreateProduct.mockResolvedValue({ item: sampleItem, message: "created" })
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
})
