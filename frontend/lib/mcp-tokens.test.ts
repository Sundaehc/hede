import { afterEach, describe, expect, it, vi } from "vitest"

import { issueMcpToken, listMcpTokens, revokeMcpToken } from "@/lib/mcp-tokens"

afterEach(() => vi.unstubAllGlobals())

describe("MCP token API", () => {
  it("uses authenticated no-store requests and explicit mutation headers", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal("fetch", fetch)
    await issueMcpToken({
      user_id: 2,
      profile: "products",
      days: 30,
      label: "office",
    })
    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/admin/mcp-tokens",
      expect.objectContaining({
        credentials: "include",
        cache: "no-store",
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Mcp-Admin": "1" },
      })
    )
    await revokeMcpToken(12)
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/auth/admin/mcp-tokens/12/revoke",
      expect.objectContaining({ method: "POST", body: "{}" })
    )
    await listMcpTokens(2)
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/auth/admin/mcp-tokens?page=2&page_size=20",
      expect.objectContaining({ cache: "no-store" })
    )
  })

  it("does not expose raw proxy response bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => {
          throw new Error("private upstream details")
        },
      })
    )
    await expect(listMcpTokens(1)).rejects.toThrow("操作未完成")
  })
})
