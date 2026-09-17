import { describe, expect, it } from "vitest"

import { packMonochromePixels } from "@/lib/local-label-print"

describe("packMonochromePixels", () => {
  it("packs black pixels into the printer's most-significant-bit-first format", () => {
    const pixels = new Uint8ClampedArray(8 * 4)
    pixels.fill(255)
    pixels[3] = 255
    pixels[4] = 0
    pixels[5] = 0
    pixels[6] = 0
    pixels[7] = 255

    expect(Array.from(packMonochromePixels(pixels, 8, 1))).toEqual([0b01000000])
  })

  it("treats transparent pixels as white", () => {
    const pixels = new Uint8ClampedArray(8 * 4)
    expect(Array.from(packMonochromePixels(pixels, 8, 1))).toEqual([0])
  })

  it("rejects widths that cannot be represented as whole bytes", () => {
    expect(() => packMonochromePixels(new Uint8ClampedArray(7 * 4), 7, 1)).toThrow(
      "标签位图宽度必须是 8 的正整数倍",
    )
  })
})
