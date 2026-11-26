import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react"
import { afterEach, expect, test, vi } from "vitest"
import type { StockPlan } from "@/lib/stock-planning"
import { StockPlanningPanel } from "./stock-planning-panel"

const { getPlan } = vi.hoisted(() => ({ getPlan: vi.fn() }))

vi.mock("@/lib/api", () => ({ getStockPlan: getPlan }))
vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ hasPermission: () => false }),
}))

afterEach(cleanup)

test("shows reference color separately and recalculates the current color's stock after a manual size edit", async () => {
  const plan: StockPlan = {
    sku: "SKU-BLUE",
    color: "蓝",
    product_name: "单鞋",
    category: "单鞋",
    size_group: "女鞋",
    season: "春秋",
    allocation_season: "春秋",
    allocation_seasons: ["春秋", "春", "秋"],
    heel_group: "高跟",
    other_colors: [{ id: 5, sku: "SKU-RED", color: "红" }],
    related_categories: ["尖头鞋"],
    sizes: ["36", "37"],
    today: "2026-11-26",
    need_by: "2026-12-09",
    stock_date: "2026-11-26",
    stock_ready: true,
    stock: { "36": 7, "37": 2 },
    source_transit: { "36": 1 },
    eligible_transit: { "36": 1 },
    sales_start: "2026-10-26",
    cutoff: "2026-11-24",
    sales_complete: true,
    sales_days: 30,
    known_volume: 0,
    sales_volume: 0,
    sales: {},
    weights: {},
    baseline: null,
    legacy_baseline: null,
    basis: "manual",
    reference: null,
    total: null,
    suggested: null,
    blocked_reason: null,
    campaigns: [],
    selected_campaign: null,
    orders: [],
    demand: {
      normal: 0,
      campaign: null,
      days: 14,
      campaign_days: 0,
      normal_shortage: 0,
      campaign_shortage: null,
    },
  }
  getPlan.mockResolvedValueOnce(plan).mockResolvedValueOnce({
    ...plan,
    total: 20,
    suggested: { "36": 8, "37": 12 },
    basis: "other_color",
    reference: {
      kind: "other_color",
      label: "SKU-RED",
      color: "红",
      weights: { "36": 12, "37": 18 },
      sales: { "36": 12, "37": 18 },
    },
  })
  render(
    <StockPlanningPanel brand="cbanner_womens" productId={1} manager={false} />
  )
  fireEvent.change(await screen.findByLabelText("补单总量（双）"), {
    target: { value: "20" },
  })
  fireEvent.change(screen.getByLabelText("配码参考"), {
    target: { value: "color:5" },
  })
  fireEvent.click(screen.getByRole("button", { name: "生成配码" }))
  expect(
    await screen.findByRole("columnheader", { name: "参考色净销" })
  ).toBeInTheDocument()
  expect(getPlan).toHaveBeenLastCalledWith(
    "cbanner_womens",
    1,
    expect.objectContaining({
      total: 20,
      season: "春秋",
      reference_product_id: 5,
    }),
    expect.any(AbortSignal)
  )
  const size36 = screen.getByRole("row", { name: /^36 / })
  const size37 = screen.getByRole("row", { name: /^37 / })
  expect(within(size36).getByRole("cell", { name: "16" })).toBeInTheDocument()
  fireEvent.change(within(size36).getByLabelText("补单 36 码"), {
    target: { value: "9" },
  })
  fireEvent.change(within(size37).getByLabelText("补单 37 码"), {
    target: { value: "11" },
  })
  expect(within(size36).getByRole("cell", { name: "17" })).toBeInTheDocument()
  expect(within(size37).getByRole("cell", { name: "13" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "复制配码" })).toBeEnabled()
})
