import { afterEach, describe, expect, it, vi } from "vitest"

import { cancelLabelsWithLocalAgent, packMonochromePixels, printLabelsWithLocalAgent } from "@/lib/local-label-print"
import { DEFAULT_PURCHASE_PRINT_TEMPLATE } from "@/components/inventory-admin/purchase-print-template-editor"

afterEach(() => vi.unstubAllGlobals())

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
