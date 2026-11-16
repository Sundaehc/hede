import { describe, expect, it } from "vitest"
import { NextRequest } from "next/server"

import { hasUnexpectedServerActionHeader, proxy } from "@/proxy"
import { PROXY_MAX_BODY_BYTES } from "@/lib/upload-limits.mjs"

describe("proxy Server Action guard", () => {
  it("rejects requests carrying a Next-Action header", () => {
    expect(hasUnexpectedServerActionHeader(new Headers({ "Next-Action": "x" }))).toBe(true)
  })

  it("allows normal application requests", () => {
    expect(hasUnexpectedServerActionHeader(new Headers())).toBe(false)
  })

  it.each(["/", "/login", "/stock-alerts/replenishment", "/api-unrelated"])(
    "rejects headerless form POSTs to page path %s before Next handles them as actions",
    async (path) => {
      const response = proxy(new NextRequest(`http://localhost${path}`, {
        method: "POST",
        headers: { "Content-Type": "multipart/form-data; boundary=diagnostic" },
      }))
      expect(response.status).toBe(405)
      expect(response.headers.get("Allow")).toBe("GET, HEAD, OPTIONS")
      expect(await response.json()).toEqual({ detail: "页面地址不支持 POST 请求，请通过 /api 接口提交" })
    },
  )

  it.each(["/api/inventory/import-template", "/api/stock-alerts/tasks", "/api"])(
    "keeps backend submissions available at %s",
    (path) => {
      const response = proxy(new NextRequest(`http://localhost${path}`, {
        method: "POST",
        headers: { "Content-Type": "multipart/form-data; boundary=import-file" },
      }))
      expect(response.headers.get("x-middleware-next")).toBe("1")
    },
  )

  it.each(["GET", "HEAD", "OPTIONS"])("allows normal page %s requests", (method) => {
    const response = proxy(new NextRequest("http://localhost/stock-alerts/replenishment", { method }))
    expect(response.headers.get("x-middleware-next")).toBe("1")
  })
})

describe("proxy request size guard", () => {
  it("returns a structured 413 for an oversized declared request", async () => {
    const request = new NextRequest("http://localhost/api/inventory/import-template/preview", {
      method: "POST",
      headers: { "Content-Length": String(PROXY_MAX_BODY_BYTES + 1) },
    })
    const response = proxy(request)
    expect(response.status).toBe(413)
    expect(await response.json()).toEqual({ detail: "请求内容过大，单个导入文件不能超过 100MB，请拆分后重试" })
  })

  it.each([String(12 * 1024 * 1024), String(PROXY_MAX_BODY_BYTES), ""])("allows supported request size %s", (contentLength) => {
    const request = new NextRequest("http://localhost/api/inventory/import-template/preview", {
      method: "POST",
      headers: contentLength ? { "Content-Length": contentLength } : {},
    })
    const response = proxy(request)
    expect(response.status).toBe(200)
    expect(response.headers.get("x-middleware-next")).toBe("1")
  })

  it("keeps the Server Action guard ahead of the size guard", async () => {
    const request = new NextRequest("http://localhost/api/inventory/import-template/preview", {
      method: "POST",
      headers: { "Next-Action": "unexpected", "Content-Length": String(PROXY_MAX_BODY_BYTES + 1) },
    })
    const response = proxy(request)
    expect(response.status).toBe(400)
    expect(await response.json()).toEqual({ detail: "当前系统不支持 Server Action 请求" })
  })
})
