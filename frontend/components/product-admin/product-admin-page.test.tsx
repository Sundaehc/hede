import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ProductAdminPage } from "@/components/product-admin/product-admin-page"
import { ApiError } from "@/lib/api"

const { mockCreateProduct, mockListProducts, mockUpdateProduct } = vi.hoisted(() => ({
  mockCreateProduct: vi.fn(),
  mockListProducts: vi.fn(),
  mockUpdateProduct: vi.fn(),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")

  return {
    ...actual,
    createProduct: mockCreateProduct,
    listProducts: mockListProducts,
    updateProduct: mockUpdateProduct,
  }
})

const NULL_FIELDS = {
  image_path: null,
  image_url: null,
  sku: null,
  original_sku: null,
  group_name: null,
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
  first_order_time: null,
}

const nullPayload = Object.fromEntries(
  Object.entries(NULL_FIELDS).filter(([k]) => k !== "image_url").map(([k]) => [k, null]),
)

const sampleResponse = {
  items: [
    {
      id: 1,
      brand: "qbd_mens" as const,
      image_path: "/images/1.jpg",
      image_url: "/images/serve/qbd_mens/1.jpg",
      sku: "SKU-001",
      original_sku: "ORIG-001",
      group_name: null,
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
      first_order_time: null,
      source_workbook: "book.xlsx",
      source_sheet: "sheet1",
      source_row_number: "2",
    },
  ],
  total: 1,
  page: 1,
  page_size: 10,
}

describe("ProductAdminPage", () => {
  beforeEach(() => {
    mockCreateProduct.mockReset()
    mockListProducts.mockReset()
    mockUpdateProduct.mockReset()
    mockListProducts.mockResolvedValue(sampleResponse)
    mockCreateProduct.mockResolvedValue({ item: sampleResponse.items[0], message: "created" })
    mockUpdateProduct.mockResolvedValue({ item: sampleResponse.items[0], message: "updated" })
  })

  it("fetches qbd_mens on first render", async () => {
    render(<ProductAdminPage />)

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenCalledWith({
        brand: "qbd_mens",
        page: 1,
        pageSize: 10,
        query: undefined,
      })
    })

    expect(screen.getByRole("heading", { name: "商品信息档案" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "千百度男鞋", selected: true })).toBeInTheDocument()
    expect(await screen.findByTestId("card-title-1")).toBeInTheDocument()
  })

  it("shows the loading state while products are being fetched", () => {
    mockListProducts.mockImplementation(() => new Promise(() => {}))

    render(<ProductAdminPage />)

    expect(screen.getByText("正在加载商品数据...")).toBeInTheDocument()
  })

  it("shows the error state when product loading fails", async () => {
    mockListProducts.mockRejectedValue(new ApiError(500, "服务异常"))

    render(<ProductAdminPage />)

    expect(await screen.findByText("加载失败")).toBeInTheDocument()
    expect(screen.getByText("服务异常")).toBeInTheDocument()
  })

  it("switching tabs fetches qbd_womens", async () => {
    const user = userEvent.setup()

    render(<ProductAdminPage />)

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenCalledWith({
        brand: "qbd_mens",
        page: 1,
        pageSize: 10,
        query: undefined,
      })
    })

    await user.click(screen.getByRole("tab", { name: "千百度女鞋" }))

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenLastCalledWith({
        brand: "qbd_womens",
        page: 1,
        pageSize: 10,
        query: undefined,
      })
    })
  })

  it("keyboard tab changes reset pagination to page 1 for the newly selected brand", async () => {
    const user = userEvent.setup()

    mockListProducts.mockImplementation(({ brand, page }: { brand: string; page: number }) => {
      if (brand === "qbd_mens" && page === 1) {
        return Promise.resolve({
          ...sampleResponse,
          total: 11,
          page: 1,
        })
      }

      if (brand === "qbd_mens" && page === 2) {
        return Promise.resolve({
          ...sampleResponse,
          total: 11,
          page: 2,
        })
      }

      if (brand === "qbd_womens") {
        return Promise.resolve({
          ...sampleResponse,
          brand: "qbd_womens",
          total: 1,
          page: 1,
        })
      }

      return Promise.resolve(sampleResponse)
    })

    render(<ProductAdminPage />)

    expect(await screen.findByText("第 1 / 2 页")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "下一页" }))

    expect(await screen.findByText("第 2 / 2 页")).toBeInTheDocument()

    screen.getByRole("tab", { name: "千百度男鞋", selected: true }).focus()
    await user.keyboard("{ArrowRight}")

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenLastCalledWith({
        brand: "qbd_womens",
        page: 1,
        pageSize: 10,
        query: undefined,
      })
    })

    expect(screen.getByRole("tab", { name: "千百度女鞋", selected: true })).toBeInTheDocument()
    expect(await screen.findByText("第 1 / 1 页")).toBeInTheDocument()
  })

  it("searching submits the current tab and query", async () => {
    const user = userEvent.setup()

    render(<ProductAdminPage />)

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenCalledWith({
        brand: "qbd_mens",
        page: 1,
        pageSize: 10,
        query: undefined,
      })
    })

    await user.click(screen.getByRole("tab", { name: "千百度女鞋" }))

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenLastCalledWith({
        brand: "qbd_womens",
        page: 1,
        pageSize: 10,
        query: undefined,
      })
    })

    await user.type(screen.getByLabelText("原始货号"), "ABC-123")
    await user.click(screen.getByRole("button", { name: "搜索" }))

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenLastCalledWith({
        brand: "qbd_womens",
        page: 1,
        pageSize: 10,
        query: "ABC-123",
      })
    })
  })

  it("opens create mode from 新增商品 and refreshes after save", async () => {
    const user = userEvent.setup()

    render(<ProductAdminPage />)

    await screen.findByTestId("card-title-1")
    await user.click(screen.getByRole("button", { name: "新增商品" }))

    expect(await screen.findByRole("heading", { name: "新增商品" })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText("品牌"), "qbd_mens")
    await user.type(document.getElementById("product-form-image-path")!, "/images/created.jpg")
    await user.type(document.getElementById("product-form-sku")!, "SKU-NEW")
    await user.type(document.getElementById("product-form-color")!, "黑色")
    await user.type(document.getElementById("product-form-year")!, "2026")
    await user.type(document.getElementById("product-form-season_category")!, "春季")
    await user.type(document.getElementById("product-form-original_sku")!, "NEW-001")
    await user.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() => {
      expect(mockCreateProduct).toHaveBeenCalledWith("qbd_mens", {
        ...nullPayload,
        original_sku: "NEW-001",
        sku: "SKU-NEW",
        color: "黑色",
        year: "2026",
        season_category: "春季",
        image_path: "/images/created.jpg",
      })
    })

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenCalledTimes(2)
    })
  })

  it("opens edit mode from row 编辑 and keeps brand fixed while saving", async () => {
    const user = userEvent.setup()

    render(<ProductAdminPage />)

    await screen.findByTestId("card-title-1")
    await user.click(screen.getByRole("button", { name: "编辑" }))

    expect(await screen.findByRole("heading", { name: "编辑商品" })).toBeInTheDocument()
    expect(screen.getByLabelText("品牌")).toBeDisabled()
    expect(screen.getByLabelText("品牌")).toHaveValue("qbd_mens")

    await user.clear(document.getElementById("product-form-color")!)
    await user.type(document.getElementById("product-form-color")!, "白色")
    await user.click(screen.getByRole("button", { name: "保存" }))

    await waitFor(() => {
      expect(mockUpdateProduct).toHaveBeenCalledWith("qbd_mens", 1, {
        ...nullPayload,
        image_path: "/images/1.jpg",
        original_sku: "ORIG-001",
        sku: "SKU-001",
        color: "白色",
        year: "2026",
        season_category: "春季",
      })
    })

    await waitFor(() => {
      expect(mockListProducts).toHaveBeenCalledTimes(2)
    })
  })
})
