import { afterEach, describe, expect, it, vi } from "vitest"

import { cancelLabelsWithLocalAgent, packMonochromePixels, printLabelsWithLocalAgent, renderLocalLabelBitmap } from "@/lib/local-label-print"
import { DEFAULT_PURCHASE_PRINT_TEMPLATE } from "@/components/inventory-admin/purchase-print-template-editor"
import type { InventoryPrintLabel, PurchasePrintTemplateConfig } from "@/lib/api"

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe("local EAN-13 label printing", () => {
  const label: InventoryPrintLabel = {
    detail_id: 1, product_code: "SKU-01", size_name: "250", size_barcode: "250", barcode: "SKU-01250",
    international_code: "0123456789012", copies: 1, brand: "cbanner_mens", brand_name: "C°BANNER",
    product_level: "合格品", color_name: "米色", upper_material: "牛皮", product_name: "皮鞋", execution_standard: "TEST", origin: "中国",
  }
  const config: PurchasePrintTemplateConfig = {
    ...DEFAULT_PURCHASE_PRINT_TEMPLATE, show_outer_border: false,
    elements: [{ ...DEFAULT_PURCHASE_PRINT_TEMPLATE.elements[9], id: "international", field: "international_code", x: 10, y: 10, width: 34, height: 20 }],
  }

  function mockCanvas() {
    const fills: { color: string; x: number; y: number; width: number; height: number }[] = []
    const context = {
      fillStyle: "#000", font: "", textAlign: "", textBaseline: "",
      save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), rect: vi.fn(), clip: vi.fn(),
      fillRect(x: number, y: number, width: number, height: number) { fills.push({ color: this.fillStyle, x, y, width, height }) },
      fillText: vi.fn(),
      measureText: (text: string) => ({ width: text.length * 8 }),
      getImageData: () => {
        const pixels = new Uint8ClampedArray(640 * 480 * 4).fill(255)
        for (const rect of fills.filter((fill) => fill.color === "#000")) {
          for (let y = rect.y; y < rect.y + rect.height; y += 1) {
            for (let x = rect.x; x < rect.x + rect.width; x += 1) {
              const offset = (y * 640 + x) * 4
              pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = 0
            }
          }
        }
        return { data: pixels }
      },
    }
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D)
    return context
  }

  it("rasterizes the international code into the agent bitmap with readable digits and EAN guards", async () => {
    const context = mockCanvas()
    const bitmap = await renderLocalLabelBitmap(label, config)
    expect(context.fillText.mock.calls.map((call) => call[0]).join("")).toBe("0123456789012")
    const bytes = Uint8Array.from(window.atob(bitmap.data_base64), (char) => char.charCodeAt(0))
    const row = Array.from({ length: 640 }, (_, x) => (bytes[90 * 80 + Math.floor(x / 8)] & (0x80 >> (x % 8))) ? "1" : "0")
    const firstBar = row.indexOf("1")
    const lastBar = row.lastIndexOf("1")
    expect(lastBar - firstBar + 1).toBe(95 * 2)
    const modules = row.slice(firstBar, lastBar + 1).filter((_bit, index) => index % 2 === 0).join("")
    expect(modules.slice(0, 3)).toBe("101")
    expect(modules.slice(45, 50)).toBe("01010")
    expect(modules.slice(-3)).toBe("101")
    expect(firstBar - 80).toBeGreaterThanOrEqual(11 * 2)
  })

  it.each(["", "123456789012", "6927335313915"])("does not send a print request when international code is invalid: %s", async (value) => {
    mockCanvas()
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    await expect(printLabelsWithLocalAgent([{ ...label, international_code: value }], config)).rejects.toThrow("SKU-01")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("draws the selected production date into the actual label bitmap", async () => {
    const context = mockCanvas()
    await renderLocalLabelBitmap({ ...label, production_date: "2026-11-06" }, {
      ...config,
      elements: [{ ...DEFAULT_PURCHASE_PRINT_TEMPLATE.elements[0], field: "production_date", label: "生产日期" }],
    })
    expect(context.fillText).toHaveBeenCalledWith("生产日期：2026-11-06", expect.any(Number), expect.any(Number))
  })

  it("prints solid horizontal lines at their saved positions without adding text or barcode pixels", async () => {
    const context = mockCanvas()
    const bitmap = await renderLocalLabelBitmap(label, {
      ...config,
      elements: [
        { ...DEFAULT_PURCHASE_PRINT_TEMPLATE.elements[0], id: "line-1", kind: "line", field: null, x: 2, y: 7.5, width: 76, height: 0.25 },
        { ...DEFAULT_PURCHASE_PRINT_TEMPLATE.elements[0], id: "line-2", kind: "line", field: null, x: 4, y: 20, width: 50, height: 0.1 },
      ],
    })
    const bytes = Uint8Array.from(window.atob(bitmap.data_base64), (char) => char.charCodeAt(0))
    const row = (y: number) => Array.from({ length: 640 }, (_, x) => !!(bytes[y * 80 + Math.floor(x / 8)] & (0x80 >> (x % 8))))
    expect(row(59).some(Boolean)).toBe(false)
    expect(row(60).filter(Boolean)).toHaveLength(608)
    expect(row(61).filter(Boolean)).toHaveLength(608)
    expect(row(60).slice(16, 624).every(Boolean)).toBe(true)
    expect(row(62).some(Boolean)).toBe(false)
    expect(row(160).filter(Boolean)).toHaveLength(400)
    expect(row(161).some(Boolean)).toBe(false)
    expect(context.fillText).not.toHaveBeenCalled()
  })
})

describe("local print cancellation", () => {
  it("does not send an already cancelled batch to the printer", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const controller = new AbortController()
    controller.abort()
    await expect(printLabelsWithLocalAgent([], DEFAULT_PURCHASE_PRINT_TEMPLATE, {
      signal: controller.signal,
    })).rejects.toMatchObject({ name: "AbortError" })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("aborts the print upload without reporting that the local service is unavailable", async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")))
    }))
    vi.stubGlobal("fetch", fetchMock)
    const print = printLabelsWithLocalAgent([], DEFAULT_PURCHASE_PRINT_TEMPLATE, {
      requestId: "a".repeat(32), signal: controller.signal,
    })
    controller.abort()
    await expect(print).rejects.toMatchObject({ name: "AbortError" })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject({ request_id: "a".repeat(32) })
  })

  it.each(["cancelled", "not_in_queue", "not_received"])("returns the agent's %s result for the exact request", async (status) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, status })))
    vi.stubGlobal("fetch", fetchMock)
    expect(await cancelLabelsWithLocalAgent("a".repeat(32))).toEqual({ ok: true, status })
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/cancel$/), expect.objectContaining({
      method: "POST", body: JSON.stringify({ request_id: "a".repeat(32) }),
    }))
  })

  it("tells users to update an older print agent rather than claiming cancellation succeeded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })))
    await expect(cancelLabelsWithLocalAgent("a".repeat(32))).rejects.toThrow("请更新打印服务")
  })

  it("does not claim cancellation when the agent cannot be reached or returns an invalid result", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, status: "unknown" })))
    vi.stubGlobal("fetch", fetchMock)
    await expect(cancelLabelsWithLocalAgent("a".repeat(32))).rejects.toThrow("未能确认取消结果")
    await expect(cancelLabelsWithLocalAgent("a".repeat(32))).rejects.toThrow("未能确认取消结果")
  })
})

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
