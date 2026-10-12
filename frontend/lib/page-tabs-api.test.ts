import { afterEach, expect, test, vi } from "vitest"

import { getPinnedPageTabs, setPageTabPinned } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("loads the authenticated account's fixed tabs", async () => {
  const response = { pinned_paths: ["/products"] }
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }))
  expect(await getPinnedPageTabs()).toEqual(response)
  expect(fetchMock).toHaveBeenCalledWith("/api/auth/me/page-tabs", expect.objectContaining({ credentials: "include" }))
})

test.each([[true, "PUT"], [false, "DELETE"]])("updates one tab's fixed state %s without a supplied user ID", async (pinned, method) => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ pinned_paths: [] }), { status: 200 }))
  await setPageTabPinned("/inventory", pinned as boolean)
  expect(fetchMock).toHaveBeenCalledWith("/api/auth/me/page-tabs", expect.objectContaining({
    method, credentials: "include", body: JSON.stringify({ page_path: "/inventory" }),
  }))
})
