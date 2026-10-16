import { createHash } from "node:crypto"
import type { IncomingMessage } from "node:http"
import { Readable } from "node:stream"
import { getCloneableBody } from "next/dist/server/body-streams"
import { configSchema } from "next/dist/server/config-schema"
import { expect, test, vi } from "vitest"

import nextConfig from "./next.config.mjs"
import { INVENTORY_IMPORT_MAX_FILE_BYTES, PROXY_MAX_BODY_BYTES } from "@/lib/upload-limits.mjs"

test("configures the supported Next.js proxy body limit with room for multipart fields", () => {
  expect(configSchema.safeParse(nextConfig).success).toBe(true)
  expect(nextConfig.experimental?.proxyClientMaxBodySize).toBe(PROXY_MAX_BODY_BYTES)
  expect(PROXY_MAX_BODY_BYTES - INVENTORY_IMPORT_MAX_FILE_BYTES).toBe(1024 * 1024)
  expect(nextConfig.experimental?.proxyTimeout).toBe(180_000)
})

test("preserves an upload larger than 10MiB through Next.js body cloning", async () => {
  const boundary = "hede-import-test-boundary"
  const payload = Buffer.concat([
    Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="large.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n`),
    Buffer.alloc(12 * 1024 * 1024, 0x61),
    Buffer.from(`\r\n--${boundary}--\r\n`),
  ])
  const chunks = []
  for (let offset = 0; offset < payload.length; offset += 64 * 1024) {
    chunks.push(payload.subarray(offset, offset + 64 * 1024))
  }
  const request = Object.assign(Readable.from(chunks), { url: "/api/inventory/import-template/preview" }) as unknown as IncomingMessage
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined)
  try {
    const sizeLimit = nextConfig.experimental?.proxyClientMaxBodySize
    if (typeof sizeLimit !== "number") throw new Error("Expected a numeric proxy body limit")
    const body = getCloneableBody(request, sizeLimit)
    const clone = body.cloneBodyStream()
    const received = []
    for await (const chunk of clone) received.push(Buffer.from(chunk))
    await body.finalize()
    const result = Buffer.concat(received)
    expect(result.length).toBe(payload.length)
    expect(createHash("sha256").update(result).digest("hex")).toBe(createHash("sha256").update(payload).digest("hex"))
    expect(result.subarray(-boundary.length - 8).toString()).toContain(`--${boundary}--`)
    const forwarded = []
    for await (const chunk of request) forwarded.push(Buffer.from(chunk))
    const forwardedBody = Buffer.concat(forwarded)
    expect(forwardedBody.length).toBe(payload.length)
    expect(createHash("sha256").update(forwardedBody).digest("hex")).toBe(createHash("sha256").update(payload).digest("hex"))
    expect(warn).not.toHaveBeenCalled()
  } finally {
    warn.mockRestore()
    request.destroy()
  }
})
