import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { ProductToolbar } from "@/components/product-admin/product-toolbar"
import { ApiError, importProducts } from "@/lib/api"
import type { ProductImportValidation } from "@/lib/product-import-validation"

const { importMock } = vi.hoisted(() => ({ importMock: vi.fn() }))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  importProducts: importMock,
  getProductImageRefreshStatus: async () => ({ in_progress: false }),
}))

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); window.sessionStorage.clear() })

function props() {
  return { brand: "cbanner_mens" as const, year: "", value: "", query: "", prefixValue: "", skuPrefix: "",
    isLoading: false, canImport: true, canRefreshImages: false, onValueChange: vi.fn(), onPrefixValueChange: vi.fn(),
    onSearch: vi.fn(), onClear: vi.fn(), onRefresh: vi.fn(), onImportComplete: vi.fn(), onCreate: vi.fn(), onMessage: vi.fn() }
}

function upload(container: HTMLElement) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]')!
  fireEvent.change(input, { target: { files: [new File(["test"], "档案.xlsx")] } })
  return input
}

test("shows every color error with archive labels, copies all pages and allows a corrected import", async () => {
  const user = userEvent.setup()
  const write = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  const validation: ProductImportValidation = { code:"product_validation", message:"发现 62 行商品的颜色或颜色代码为空，请补齐后重新导入；本次未导入任何数据。", total:62,
    errors:Array.from({length:62}, (_,i) => ({ row_number:i+2, product_code:`000SKU${i}`, brand:"cbanner_mens", summary:"商品表", reason:i%2 ? "颜色不能为空" : "颜色代码不能为空" })) }
  importMock.mockRejectedValueOnce(new ApiError(400, validation))
  const callbacks = props()
  const { container } = render(<ProductToolbar {...callbacks} />)
  const input = upload(container)
  const dialog = within(await screen.findByRole("dialog", { name:"商品档案导入未完成" }))
  expect(dialog.getByRole("columnheader", {name:"货号"})).toBeInTheDocument()
  expect(dialog.getByRole("columnheader", {name:"工作表"})).toBeInTheDocument()
  expect(dialog.queryByRole("columnheader", {name:"单据摘要"})).not.toBeInTheDocument()
  expect(within(dialog.getByRole("region", {name:"商品资料错误明细"})).getAllByRole("row")).toHaveLength(51)
  await user.click(dialog.getByRole("button", {name:"下一页错误"}))
  expect(dialog.getByText("000SKU61")).toBeInTheDocument()
  await user.click(dialog.getByRole("button", {name:"复制全部错误"}))
  const copied = write.mock.calls[0][0]
  expect(copied.split("\n")).toHaveLength(63)
  expect(copied).toContain("Excel 行号\t货号\t品牌\t工作表\t错误原因")
  expect(copied).toContain("2\t000SKU0\t千百度男鞋\t商品表\t颜色代码不能为空")
  expect(copied).toContain("63\t000SKU61\t千百度男鞋\t商品表\t颜色不能为空")
  expect(callbacks.onImportComplete).not.toHaveBeenCalled()
  expect(callbacks.onClear).not.toHaveBeenCalled()
  expect(callbacks.onMessage).not.toHaveBeenCalled()
  expect(input.value).toBe("")
  await user.click(dialog.getByRole("button", {name:"关闭"}))
  importMock.mockResolvedValueOnce({ created:1, updated:0, skus:["FIXED"], message:"导入完成" })
  upload(container)
  await waitFor(() => expect(callbacks.onImportComplete).toHaveBeenCalledWith(["FIXED"]))
  expect(callbacks.onMessage).toHaveBeenCalledWith("导入完成", "导入完成")
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

test("keeps ordinary import errors readable and does not claim success", async () => {
  importMock.mockRejectedValueOnce(new ApiError(400,"第 2 行导入失败：供应商不一致"))
  const callbacks = props()
  const {container} = render(<ProductToolbar {...callbacks} />)
  upload(container)
  await waitFor(() => expect(callbacks.onMessage).toHaveBeenCalledWith("导入失败","第 2 行导入失败：供应商不一致"))
  expect(callbacks.onImportComplete).not.toHaveBeenCalled()
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

test("product import API preserves every server error and does not publish a success", async () => {
  const detail: ProductImportValidation = { code:"product_validation", message:"颜色不能为空，本次未导入任何数据。", total:1,
    errors:[{row_number:3, product_code:"00001", brand:"ni", summary:"商品表", reason:"颜色不能为空"}] }
  const fetch = vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({detail}),{status:400}))
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  await expect(actual.importProducts("ni",new File(["test"],"档案.xlsx"))).rejects.toMatchObject({status:400, message:detail.message, validation:detail})
  expect(fetch).toHaveBeenCalledOnce()
  expect(importProducts).toBe(importMock)
})
