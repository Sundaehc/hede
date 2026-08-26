import { beforeEach, expect, test, vi } from "vitest"

import { importPurchaseInventory } from "@/lib/api"


beforeEach(() => {
  vi.restoreAllMocks()
})

test("importPurchaseInventory extracts FastAPI detail from an error response", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        detail: "商品编码 NAE2645009X04245 不是由商品信息档案中的已有商品构成，请检查货号、颜色和尺码",
      }),
      {
        status: 400,
        headers: { "Content-Type": "application/json" },
      },
    ),
  )

  await expect(
    importPurchaseInventory({
      file: new File(["test"], "采购单.xlsx"),
      supplier: "测试供应商",
      warehouse: "测试仓库",
      document_type: "进货订单",
      handler: "测试用户",
      summary: "测试导入",
    }),
  ).rejects.toMatchObject({
    status: 400,
    message: "商品编码 NAE2645009X04245 不是由商品信息档案中的已有商品构成，请检查货号、颜色和尺码",
  })
})
