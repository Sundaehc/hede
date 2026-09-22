import { afterEach, expect, test, vi } from "vitest"

import { getSavedProductCopywriting, regenerateProductCopywriting } from "@/lib/api"

afterEach(() => vi.unstubAllGlobals())

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
