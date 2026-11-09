import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, expect, test, vi } from "vitest"

import { InventoryImportError } from "@/components/inventory-admin/inventory-import-error"
import type { ProductImportValidation } from "@/lib/product-import-validation"

afterEach(() => { cleanup(); vi.restoreAllMocks() })

function validation(total = 62): ProductImportValidation {
  return {
    code: "product_validation", message: `发现 ${total} 条商品资料错误，本次未导入任何数据，请联系商品部。`, total,
    errors: Array.from({ length: total }, (_, i) => ({
      row_number: i + 2, product_code: `000${String(i).padStart(3, "0")}`, brand: i % 2 ? "cbanner_womens" : "custom",
      summary: `单据${i % 3}`, reason: i % 2 ? "商品编码不符合条码规则，请检查尺码" : "未匹配到商品信息档案",
    })),
  }
}

test("all errors are reachable with bounded rendering and copying includes other pages", async () => {
  const user = userEvent.setup()
  const write = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  const detail = validation()
  render(<InventoryImportError message={detail.message} validation={detail} brands={[{ value: "custom", label: "配置品牌" }]} />)
  const region = within(screen.getByRole("region", { name: "商品资料错误明细" }))
  expect(region.getAllByRole("row")).toHaveLength(51)
  expect(screen.queryByText("000061")).not.toBeInTheDocument()
  expect(region.getAllByText("配置品牌")).toHaveLength(25)
  expect(region.getAllByText("千百度女鞋")).toHaveLength(25)
  await user.click(screen.getByRole("button", { name: "下一页错误" }))
  expect(region.getAllByRole("row")).toHaveLength(13)
  expect(region.getByText("000061")).toBeInTheDocument()
  expect(screen.getByRole("status")).toHaveTextContent("第 51–62 条，共 62 条")
  await user.click(screen.getByRole("button", { name: "复制全部错误" }))
  const copied = write.mock.calls[0][0]
  expect(copied.split("\n")).toHaveLength(63)
  expect(copied).toContain("2\t000000\t配置品牌\t单据0\t未匹配到商品信息档案")
  expect(copied).toContain("63\t000061\t千百度女鞋\t单据1\t商品编码不符合条码规则，请检查尺码")
  expect(screen.getByRole("button", { name: "已复制全部错误" })).toHaveFocus()
  await user.click(screen.getByRole("button", { name: "上一页错误" }))
  expect(region.getByText("000000")).toBeInTheDocument()
})

test("clipboard failure preserves readable rows and permits retry", async () => {
  const user = userEvent.setup()
  const write = vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied")).mockResolvedValue()
  const detail = validation(2)
  detail.errors[0].product_code = ""
  render(<InventoryImportError message={detail.message} validation={detail} />)
  await user.click(screen.getByRole("button", { name: "复制全部错误" }))
  expect(screen.getByRole("status")).toHaveTextContent("复制失败")
  expect(screen.getByText("（未填写）")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "复制全部错误" }))
  expect(write).toHaveBeenCalledTimes(2)
  expect(screen.getByRole("button", { name: "已复制全部错误" })).toBeInTheDocument()
})
