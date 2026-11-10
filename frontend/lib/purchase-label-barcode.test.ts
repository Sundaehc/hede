import { describe, expect, it } from "vitest"

import { createPurchaseBarcodeLayout } from "@/lib/purchase-label-barcode"

describe("purchase label Code128 layout", () => {
  it.each(["TEST-01230", "QT653891S7301230", "ACTUAL-01BLACKEU35", "00123456789012345678901234"])(
    "keeps %s on whole printer dots with a ten-module quiet zone on both sides",
    (value) => {
      const layout = createPurchaseBarcodeLayout(value, 576, 81)
      const first = layout.bars[0]
      const last = layout.bars.at(-1)!
      expect(Number.isInteger(layout.moduleWidth)).toBe(true)
      expect(layout.moduleWidth).toBeGreaterThanOrEqual(2)
      expect(first.x).toBeGreaterThanOrEqual(layout.moduleWidth * 10)
      expect(576 - last.x - last.width).toBeGreaterThanOrEqual(layout.moduleWidth * 10)
      expect(Math.abs(first.x - (576 - last.x - last.width))).toBeLessThanOrEqual(1)
      layout.bars.forEach((bar, index) => {
        expect(bar.width % layout.moduleWidth).toBe(0)
        expect(Number.isInteger(bar.x)).toBe(true)
        if (index > 0) {
          const previous = layout.bars[index - 1]
          expect((bar.x - previous.x - previous.width) % layout.moduleWidth).toBe(0)
        }
      })
    },
  )

  it("accounts for the element border when reserving quiet zones", () => {
    // TEST-01230 has 134 modules, plus 20 modules for quiet zones.
    const layout = createPurchaseBarcodeLayout("TEST-01230", 310, 81, true)
    expect(layout.moduleWidth).toBe(2)
    expect(layout.bars[0].x).toBe(21)
    expect(layout.y).toBe(1)
    expect(layout.barHeight).toBe(79)
    expect(() => createPurchaseBarcodeLayout("TEST-01230", 309, 81, true)).toThrow("打印区域不足")
  })

  it("refuses a long code instead of compressing bars or printing one-dot modules", () => {
    expect(() => createPurchaseBarcodeLayout("A".repeat(100), 576, 81)).toThrow("请增大模板中的条码宽度")
  })

  it("identifies a code that cannot be encoded as Code128", () => {
    expect(() => createPurchaseBarcodeLayout("测试鞋", 576, 81)).toThrow("无法生成 Code128")
  })
})
