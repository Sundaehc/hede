import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { SizeGroupsPage } from "@/components/size-groups/size-groups-page"
import { ColorBarcodeManagementPage } from "@/components/color-barcodes/color-barcode-management-page"
import { AuxiliaryAttributeManagementPage } from "@/components/auxiliary-attributes/auxiliary-attribute-management-page"
import { ProductTagManagementPage } from "@/components/product-tags/product-tag-management-page"

const { sizeSave, colorSave, attributeSave, tagSave } = vi.hoisted(() => ({
  sizeSave: vi.fn(), colorSave: vi.fn(), attributeSave: vi.fn(), tagSave: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { id: 12, department_code: "财务部", role_code: "finance_user" } }),
}))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listSizeGroups: async () => ({ items: [{ id: 7, name: "测试尺码组", items: [{ id: 1, size_name: "35", barcode: "35" }], product_count: 0 }] }),
  updateSizeGroup: sizeSave,
  listColorBarcodeBrands: async () => ({ items: [{ brand: "cbanner_mens", brand_label: "千百度男鞋", total: 1 }] }),
  listManagedColorBarcodes: async () => ({ items: [{ id: 7, brand: "cbanner_mens", color_barcode: "02", color_name: "黑色" }], total: 1 }),
  updateColorBarcode: colorSave,
  getProductAuxiliaryAttributeMetadata: async () => ({ scopes: [{ value: "cbanner_mens", label: "千百度男鞋", total: 1 }], attribute_types: [{ value: "品名" }] }),
  listManagedProductAuxiliaryAttributes: async () => ({ items: [{ id: 7, brand_scope: "cbanner_mens", attribute_type: "品名", attribute_name: "休闲鞋" }], total: 1 }),
  updateProductAuxiliaryAttribute: attributeSave,
  getProductTagMetadata: async () => ({ groups: ["风格"] }),
  listProductTags: async () => ({ items: [{ id: 7, tag_name: "休闲", tag_group: "风格", sort_order: 1, is_active: true }] }),
  updateProductTag: tagSave,
}))

beforeEach(() => {
  vi.clearAllMocks()
  window.sessionStorage.clear()
  sizeSave.mockResolvedValue({ item: { id: 7, name: "财务尺码组", items: [{ id: 1, size_name: "35", barcode: "35" }], product_count: 0 } })
  colorSave.mockResolvedValue({ message: "已保存" })
  attributeSave.mockResolvedValue({ message: "已保存" })
  tagSave.mockResolvedValue({ message: "已保存" })
})
afterEach(cleanup)

test("finance can load and save a size group", async () => {
  const user = userEvent.setup()
  render(<SizeGroupsPage />)
  const name = await screen.findByLabelText("尺码组名称")
  await waitFor(() => expect(name).toHaveValue("测试尺码组"))
  expect(screen.getByRole("button", { name: "新增尺码组" })).toBeEnabled()
  expect(screen.getByRole("button", { name: "删除尺码组" })).toBeEnabled()
  await user.clear(name)
  await user.type(name, "财务尺码组")
  await user.click(screen.getByRole("button", { name: "保存" }))
  await waitFor(() => expect(sizeSave).toHaveBeenCalledWith(7, expect.objectContaining({ name: "财务尺码组" })))
})

test("finance can load and edit a color", async () => {
  const user = userEvent.setup()
  render(<ColorBarcodeManagementPage />)
  await user.click(await screen.findByRole("button", { name: "编辑 黑色" }))
  const dialog = within(screen.getByRole("dialog", { name: "编辑颜色" }))
  const name = dialog.getByLabelText("颜色名称")
  await user.clear(name)
  await user.type(name, "白色")
  await user.click(dialog.getByRole("button", { name: "保存" }))
  await waitFor(() => expect(colorSave).toHaveBeenCalledWith(7, expect.objectContaining({ color_name: "白色" })))
})

test("finance can load and edit an auxiliary attribute", async () => {
  const user = userEvent.setup()
  render(<AuxiliaryAttributeManagementPage />)
  await user.click(await screen.findByRole("button", { name: "编辑 休闲鞋" }))
  const dialog = within(screen.getByRole("dialog", { name: "编辑辅助属性" }))
  const name = dialog.getByLabelText("属性值")
  await user.clear(name)
  await user.type(name, "运动鞋")
  await user.click(dialog.getByRole("button", { name: "保存" }))
  await waitFor(() => expect(attributeSave).toHaveBeenCalledWith(7, expect.objectContaining({ attribute_name: "运动鞋" })))
})

test("finance can load and save a product tag", async () => {
  const user = userEvent.setup()
  render(<ProductTagManagementPage />)
  expect(screen.getByRole("button", { name: "从商品档案重建" })).toBeEnabled()
  await user.click(await screen.findByRole("button", { name: "编辑休闲" }))
  const dialog = within(screen.getByRole("dialog", { name: "编辑商品标签" }))
  const name = dialog.getByLabelText("标签名称 *")
  await user.clear(name)
  await user.type(name, "商务")
  await user.click(dialog.getByRole("button", { name: "保存" }))
  await waitFor(() => expect(tagSave).toHaveBeenCalledWith(7, expect.objectContaining({ tag_name: "商务" })))
})
