import { afterEach, expect, test, vi } from "vitest"

import { getProductCopywritingHistory, getProductCopywritingHistoryVersion, getSavedProductCopywriting, regenerateProductCopywriting } from "@/lib/api"

afterEach(() => vi.unstubAllGlobals())

test("history list and detail only read uncached product-scoped endpoints", async () => {
  const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [], next_before_id: null }), { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  await getProductCopywritingHistory("brand with space", 7)
  await getProductCopywritingHistory("brand with space", 7, 23)
  await getProductCopywritingHistoryVersion("brand with space", 7, 11)
  const options = expect.objectContaining({ method: "GET", cache: "no-store", credentials: "include" })
  expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/product-copywriting/brand%20with%20space/7/history", options)
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/product-copywriting/brand%20with%20space/7/history?before_id=23", options)
  expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/product-copywriting/brand%20with%20space/7/history/11", options)
})

test("history preserves permission and unavailable errors without falling back to generation", async () => {
  const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ detail: "无权查看历史版本" }), { status: 403 }))
  vi.stubGlobal("fetch", fetchMock)
  await expect(getProductCopywritingHistory("cbanner_womens", 7)).rejects.toThrow("无权查看历史版本")
  await expect(getProductCopywritingHistoryVersion("cbanner_womens", 7, 11)).rejects.toThrow("无权查看历史版本")
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

const result = { status: "completed", item: { content: "数据库已保存的提示词", model: "doubao-seed-pro" }, message: "" }

test("reads saved content with GET and deduplicates simultaneous reads without generating", async () => {
  let finish: (value: Response) => void = () => undefined
  const fetchMock = vi.fn((_url: string, _init: RequestInit) => new Promise<Response>((resolve) => { finish = resolve }))
  vi.stubGlobal("fetch", fetchMock)
  const first = getSavedProductCopywriting("custom_brand", 7)
  expect(getSavedProductCopywriting("custom_brand", 7)).toBe(first)
  expect(fetchMock).toHaveBeenCalledOnce()
  expect(fetchMock).toHaveBeenCalledWith("/api/product-copywriting/custom_brand/7", expect.objectContaining({ method: "GET", cache: "no-store", credentials: "include" }))
  expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("body")
  finish(new Response(JSON.stringify(result), { status: 200 }))
  await expect(first).resolves.toEqual(result)
  fetchMock.mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }))
  await getSavedProductCopywriting("custom_brand", 7)
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

test.each(["missing", "pending", "running", "failed"])("returns %s status without automatic generation or polling", async (status) => {
  const response = { status, item: null, message: "暂无内容" }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  await expect(getSavedProductCopywriting("cbanner_womens", 8)).resolves.toEqual(response)
  expect(fetchMock).toHaveBeenCalledOnce()
})

test("failed reads can be retried without a model submission", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "权限不足" }), { status: 403 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(result), { status: 200 }))
  vi.stubGlobal("fetch", fetchMock)
  await expect(getSavedProductCopywriting("cbanner_womens", 9)).rejects.toThrow("权限不足")
  await expect(getSavedProductCopywriting("cbanner_womens", 9)).resolves.toEqual(result)
  expect(fetchMock.mock.calls.every(([, init]) => init.method === "GET")).toBe(true)
})

test("regeneration uses an authenticated POST endpoint", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "running", message: "已提交" }), { status: 202 }))
  vi.stubGlobal("fetch", fetchMock)
  await expect(regenerateProductCopywriting("cbanner_womens", 7)).resolves.toEqual({ status: "running", message: "已提交" })
  expect(fetchMock).toHaveBeenCalledWith("/api/product-copywriting/cbanner_womens/7/regenerate", expect.objectContaining({ method: "POST", credentials: "include" }))
})

test("edited prompt is sent exactly in the regeneration request body", async () => {
  const inputPrompt = "  修改后的提示词\n保留完整文本  "
  const response = { status: "running", message: "已提交", input_prompt: inputPrompt }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 202 }))
  vi.stubGlobal("fetch", fetchMock)
  await expect(regenerateProductCopywriting("cbanner_womens", 7, inputPrompt)).resolves.toEqual(response)
  expect(fetchMock).toHaveBeenCalledWith("/api/product-copywriting/cbanner_womens/7/regenerate", expect.objectContaining({
    method: "POST", credentials: "include", body: JSON.stringify({ input_prompt: inputPrompt }),
  }))
})
