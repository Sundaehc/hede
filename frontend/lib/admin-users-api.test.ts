import { afterEach, expect, test, vi } from "vitest"

import { listAdminUsers } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("serializes a trimmed name filter with user pagination", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })
  )

  await listAdminUsers({ page: 2, pageSize: 50, nameQuery: " 张 " })

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/admin/users?page=2&page_size=50&name_query=%E5%BC%A0",
    expect.objectContaining({ credentials: "include" })
  )
})

test.each([undefined, "", "   "])("omits blank name filter %s", async (nameQuery) => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })
  )

  await listAdminUsers({ page: 1, pageSize: 20, nameQuery })

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/admin/users?page=1&page_size=20",
    expect.any(Object)
  )
})
