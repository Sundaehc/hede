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

describe("purchase label EAN-13 layout", () => {
  it.each(["6927335313916", "4006381333931", "5901234123457", "0123456789012"])(
    "encodes all thirteen digits of %s with guards, readable digits and whole-dot modules",
    (value) => {
      const layout = createPurchaseBarcodeLayout(value, 272, 160, false, "EAN13")
      expect(layout.moduleWidth).toBe(2)
      expect(layout.text.map((text) => text.value).join("")).toBe(value)
      const first = layout.bars[0]
      const last = layout.bars.at(-1)!
      expect(last.x + last.width - first.x).toBe(95 * layout.moduleWidth)
      expect(first.x).toBeGreaterThanOrEqual(11 * layout.moduleWidth)
      expect(272 - last.x - last.width).toBeGreaterThanOrEqual(7 * layout.moduleWidth)
      const bits = Array.from({ length: 95 }, () => "0")
      for (const bar of layout.bars) {
        expect(Number.isInteger(bar.x)).toBe(true)
        expect(bar.width % layout.moduleWidth).toBe(0)
        const start = (bar.x - first.x) / layout.moduleWidth
        bits.fill("1", start, start + bar.width / layout.moduleWidth)
      }
      expect(bits.slice(0, 3).join("")).toBe("101")
      expect(bits.slice(45, 50).join("")).toBe("01010")
      expect(bits.slice(92).join("")).toBe("101")
      const leftPatterns = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
      const inverse = (text: string) => text.replace(/[01]/g, (bit) => bit === "1" ? "0" : "1")
      const rightPatterns = leftPatterns.map(inverse)
      const evenPatterns = rightPatterns.map((text) => text.split("").reverse().join(""))
      let parity = ""
      let digits = ""
      for (let index = 0; index < 6; index += 1) {
        const pattern = bits.slice(3 + index * 7, 10 + index * 7).join("")
        const odd = leftPatterns.indexOf(pattern)
        parity += odd >= 0 ? "L" : "G"
        digits += String(odd >= 0 ? odd : evenPatterns.indexOf(pattern))
      }
      const prefix = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"].indexOf(parity)
      for (let index = 0; index < 6; index += 1) {
        digits += String(rightPatterns.indexOf(bits.slice(50 + index * 7, 57 + index * 7).join("")))
      }
      expect(String(prefix) + digits).toBe(value)
      expect(layout.bars[0].height).toBeGreaterThan(layout.barHeight)
      expect(layout.text[0].x).toBeLessThan(first.x)
      expect(layout.text.every((text) => text.y < 160)).toBe(true)
    },
  )

  it.each(["123456789012", "12345678901234", "EAN1234567890", "692733531391６"])("rejects a value that is not thirteen ASCII digits: %s", (value) => {
    expect(() => createPurchaseBarcodeLayout(value, 272, 160, false, "EAN13")).toThrow("必须是 13 位数字")
  })

  it("rejects missing values and invalid checksums without fabricating a code", () => {
    expect(() => createPurchaseBarcodeLayout("", 272, 160, false, "EAN13")).toThrow("未填写国际码")
    expect(() => createPurchaseBarcodeLayout("6927335313915", 272, 160, false, "EAN13")).toThrow("校验码不正确")
  })

  it("rejects areas that would compress the barcode or clip its readable digits", () => {
    expect(() => createPurchaseBarcodeLayout("6927335313916", 233, 160, false, "EAN13")).toThrow("打印区域不足")
    expect(() => createPurchaseBarcodeLayout("6927335313916", 272, 50, false, "EAN13")).toThrow("打印区域不足")
  })
})
