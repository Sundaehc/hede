import { describe, expect, it } from "vitest"

import { hasUnexpectedServerActionHeader } from "@/proxy"

describe("proxy Server Action guard", () => {
  it("rejects requests carrying a Next-Action header", () => {
    expect(hasUnexpectedServerActionHeader(new Headers({ "Next-Action": "x" }))).toBe(true)
  })

  it("allows normal application requests", () => {
    expect(hasUnexpectedServerActionHeader(new Headers())).toBe(false)
  })
})
