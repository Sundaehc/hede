import { afterEach, expect, test, vi } from "vitest"
import { listInventoryPrintLabels } from "./api"
import {
  DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER,
  normalizePurchaseDetailColumnOrder,
} from "./purchase-detail-columns"

afterEach(() => vi.restoreAllMocks())

test("selected label requests preserve the abort signal and repeat detail_ids parameters", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify({ items: [], label_count: 0 }))
    )
  const { signal } = new AbortController()
  await listInventoryPrintLabels(42, signal, [102, 103])
  expect(fetch).toHaveBeenCalledWith(
    "/api/inventory/42/print-labels?detail_ids=102&detail_ids=103",
    expect.objectContaining({ signal, cache: "no-store" })
  )
})

test("empty selection cannot fall back to printing the entire order", async () => {
  const fetch = vi.spyOn(globalThis, "fetch")
  await expect(listInventoryPrintLabels(42, undefined, [])).rejects.toThrow(
    "请先勾选要打印的明细"
  )
  expect(fetch).not.toHaveBeenCalled()
})

test("corrupt or older saved columns retain valid order and include all current fields exactly once", () => {
  const result = normalizePurchaseDetailColumnOrder([
    "amount",
    "unknown",
    "amount",
    null,
    "remark",
  ])
  expect(result.slice(0, 2)).toEqual(["amount", "remark"])
  expect(result).toHaveLength(DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER.length)
  expect(new Set(result)).toEqual(new Set(DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER))
  expect(normalizePurchaseDetailColumnOrder(null)).toEqual(
    DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER
  )
})
