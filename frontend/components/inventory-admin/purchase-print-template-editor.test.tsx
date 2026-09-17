import { describe, expect, it } from "vitest"

import {
  applyOuterBorderDrag,
  resolvePurchasePrintElementText,
} from "@/components/inventory-admin/purchase-print-template-editor"
import type {
  InventoryPrintLabel,
  PurchasePrintTemplateElement,
} from "@/lib/api"

const label: InventoryPrintLabel = {
  detail_id: 1,
  product_code: "TEST-01",
  size_name: "230",
  size_barcode: "230",
  barcode: "TEST-01230",
  copies: 1,
  brand: "cbanner_womens",
  brand_name: "C°BANNER",
  product_level: "合格品",
  color_name: "黑色",
  upper_material: "牛皮",
  product_name: "女鞋",
  execution_standard: "TEST",
  origin: "中国",
}

const levelElement: PurchasePrintTemplateElement = {
  id: "level",
  kind: "text",
  field: "product_level",
  label: "等级",
  text: "",
  x: 0,
  y: 0,
  width: 20,
  height: 5,
  font_size: 9,
  bold: false,
  underline: false,
  align: "left",
  show_label: true,
  border: false,
  wrap: false,
}

describe("resolvePurchasePrintElementText", () => {
  it("uses the template's custom product level", () => {
    expect(
      resolvePurchasePrintElementText(
        { ...levelElement, text: "一等品" },
        label,
      ),
    ).toBe("等级：一等品")
  })

  it("falls back to the label data when the custom level is empty", () => {
    expect(resolvePurchasePrintElementText(levelElement, label)).toBe("等级：合格品")
  })
})

describe("applyOuterBorderDrag", () => {
  const border = { x: 2, y: 3, width: 74, height: 54, line_width: 0.25 }

  it("moves the border without leaving the paper", () => {
    expect(applyOuterBorderDrag(border, "move", 20, 20, 80, 60)).toEqual({
      ...border,
      x: 6,
      y: 6,
    })
  })

  it("resizes from the northwest corner while keeping the opposite corner fixed", () => {
    expect(applyOuterBorderDrag(border, "nw", 3, 2, 80, 60)).toEqual({
      ...border,
      x: 5,
      y: 5,
      width: 71,
      height: 52,
    })
  })

  it("clamps southeast resizing to the paper boundary", () => {
    expect(applyOuterBorderDrag(border, "se", 20, 20, 80, 60)).toEqual({
      ...border,
      width: 78,
      height: 57,
    })
  })
})
