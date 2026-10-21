import { afterEach, expect, test, vi } from "vitest"

import { getFactoryChannelDashboard } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test("serializes dashboard filters and cache bypass while forwarding abort signal", async () => {
  const controller = new AbortController()
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 200 }))
  await getFactoryChannelDashboard({
    brand: "cbanner_mens",
    salesYear: 2025,
    productYear: "2024",
    dateStart: "2025-01-01",
    dateEnd: "2025-01-02",
    cacheBust: "refresh-1",
  }, { signal: controller.signal })
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/product-goods/factory-channel-dashboard?brand=cbanner_mens&sales_year=2025&product_year=2024&date_start=2025-01-01&date_end=2025-01-02&cache_bust=refresh-1",
    expect.objectContaining({ credentials: "include", signal: controller.signal }),
  )
})

test("omits unset optional filters", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 200 }))
  await getFactoryChannelDashboard({ brand: "cbanner_womens" })
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/product-goods/factory-channel-dashboard?brand=cbanner_womens",
    expect.any(Object),
  )
})
