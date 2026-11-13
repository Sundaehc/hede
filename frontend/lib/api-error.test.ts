import { afterEach, expect, test, vi } from "vitest"

import { getCurrentUser, getInventoryTemplateTask, importInventory, previewInventoryTemplate, updateProduct } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

const gatewayHtml = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1><hr>nginx/1.24.0 (Ubuntu)</body></html>"

test("preserves posted-product confirmation data and submits the reviewed token only on retry", async () => {
  const warning = { code: "posted_product_change_confirmation", message: "该商品已过账，是否继续变更？",
    confirmation_token: "a".repeat(64), document_count: 1, detail_count: 1,
    changes: [{ field: "sku", label: "商品货号", before: "OLD", after: "NEW" }],
    documents: [{ id: 1, document_number: "TEST-POSTED", document_type: "进货单", date: "2026-11-13", detail_count: 1 }] }
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ detail: warning }), { status: 409 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ item: { sku: "NEW" }, message: "updated" })))
  await expect(updateProduct("cbanner_mens", 7, { sku: "NEW" })).rejects.toMatchObject({ status: 409, message: warning.message, postedChange: warning, validation: null })
  expect(fetchMock.mock.calls[0][0]).toBe("/api/products/cbanner_mens/7")
  await updateProduct("cbanner_mens", 7, { sku: "NEW" }, warning.confirmation_token)
  expect(fetchMock.mock.calls[1][0]).toBe(`/api/products/cbanner_mens/7?posted_change_confirmation=${warning.confirmation_token}`)
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ brand: "cbanner_mens", payload: { sku: "NEW" } })
})

test.each([
  [502, "服务连接暂时中断（502）"],
  [503, "服务暂时不可用（503）"],
  [504, "服务器响应超时（504）"],
] as const)("converts a %s gateway page into a readable error", async (status, message) => {
  const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(gatewayHtml, { status, headers: { "Content-Type": "text/html" } }),
  )
  await expect(getCurrentUser()).rejects.toMatchObject({ status, message: expect.stringContaining(message) })
  expect(fetchSpy).toHaveBeenCalledTimes(1)
})

test("a failed upload retains the gateway status and tells users to verify before resubmitting", async () => {
  const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(new Response(gatewayHtml, { status: 502 }))
  await expect(importInventory(new File(["data"], "orders.xlsx"))).rejects.toMatchObject({
    status: 502,
    message: expect.stringContaining("请先核对结果，避免重复提交"),
  })
  expect(fetchSpy).toHaveBeenCalledTimes(1)
})

test("background task polling uses the same gateway error handling", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response(gatewayHtml, { status: 502 }))
  await expect(getInventoryTemplateTask("a".repeat(32))).rejects.toMatchObject({
    status: 502,
    message: expect.stringContaining("服务连接暂时中断"),
  })
})

test("keeps the server's business validation message", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "商品未匹配，请联系商品部" }), { status: 400 }),
  )
  await expect(getCurrentUser()).rejects.toMatchObject({ status: 400, message: "商品未匹配，请联系商品部" })
})

test.each([
  ["text/html; charset=utf-8", "upstream unavailable"],
  ["text/plain", "<!doctype html><html><body>Server error</body></html>"],
  ["application/json", JSON.stringify({ detail: gatewayHtml })],
  ["application/json", "null"],
  ["text/plain", ""],
])("does not expose an HTML server page (%s)", async (contentType, body) => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(body, { status: 502, headers: { "Content-Type": contentType } }),
  )
  await expect(getCurrentUser()).rejects.toMatchObject({ status: 502, message: expect.stringContaining("服务连接暂时中断") })
})

test("hides HTML for other server errors", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response(gatewayHtml, { status: 500 }))
  await expect(getCurrentUser()).rejects.toMatchObject({ status: 500, message: "请求失败（500），请稍后重试或联系管理员。" })
})

test("preserves plain text business errors", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response("无权访问该功能", { status: 403 }))
  await expect(getCurrentUser()).rejects.toMatchObject({ status: 403, message: "无权访问该功能" })
})

test.each(["Internal Server Error", "", " INTERNAL SERVER ERROR\n"])("explains an unhandled 500 during template preview (%s)", async (body) => {
  const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(new Response(body, { status: 500 }))
  await expect(previewInventoryTemplate(new File(["data"], "history.xlsx"))).rejects.toMatchObject({
    status: 500, message: expect.stringContaining("服务器处理异常（500），请联系管理员检查后端日志"),
  })
  expect(fetchSpy).toHaveBeenCalledTimes(1)
})
