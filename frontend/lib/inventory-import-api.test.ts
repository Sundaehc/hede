import { beforeEach, expect, test, vi } from "vitest"

import { importInventory, importInventoryTemplate, importPurchaseInventory, previewInventoryTemplate, previewPurchaseInventory, replaceDetailsFromExcel, submitInventoryTemplateTask } from "@/lib/api"
import { INVENTORY_IMPORT_MAX_FILE_BYTES } from "@/lib/upload-limits.mjs"


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

const purchaseFields = {
  supplier: "测试供应商", warehouse: "测试仓库", document_type: "进货订单",
  handler: "测试用户", summary: "测试导入",
}

const importOperations: Array<{ name: string; path: string; submit: (file: File) => Promise<unknown> }> = [
  { name: "legacy import", path: "/api/inventory/import", submit: (file: File) => importInventory(file) },
  { name: "purchase preview", path: "/api/inventory/import-purchase", submit: (file: File) => previewPurchaseInventory({ ...purchaseFields, file }) },
  { name: "purchase import", path: "/api/inventory/import-purchase", submit: (file: File) => importPurchaseInventory({ ...purchaseFields, file }) },
  { name: "template preview", path: "/api/inventory/import-template/preview", submit: (file: File) => previewInventoryTemplate(file) },
  { name: "template import", path: "/api/inventory/import-template", submit: (file: File) => importInventoryTemplate({ file, brand: "cbanner_mens", decisions: {} }) },
  { name: "background template import", path: "/api/inventory/import-template/tasks/" + "a".repeat(32), submit: (file: File) => submitInventoryTemplateTask({ taskId: "a".repeat(32), file, brand: "cbanner_mens", decisions: {} }) },
  { name: "detail reimport", path: "/api/inventory/7/details/import-replace", submit: (file: File) => replaceDetailsFromExcel({ documentId: 7, file }) },
]

test.each(importOperations)("$name rejects files above 100MiB before sending", async ({ submit }) => {
  const fetchSpy = vi.spyOn(global, "fetch")
  const file = new File(["test"], "oversized.xlsx")
  Object.defineProperty(file, "size", { value: INVENTORY_IMPORT_MAX_FILE_BYTES + 1 })
  await expect(Promise.resolve().then(() => submit(file))).rejects.toMatchObject({
    status: 413, message: "导入文件不能超过 100MB，请拆分 Excel 后重试",
  })
  expect(fetchSpy).not.toHaveBeenCalled()
})

test.each(importOperations)("$name accepts the 100MiB file boundary and preserves multipart upload", async ({ path, submit }) => {
  const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ created: 1, total: 1 })))
  const file = new File(["test"], "boundary.xlsx")
  Object.defineProperty(file, "size", { value: INVENTORY_IMPORT_MAX_FILE_BYTES })
  await submit(file)
  expect(fetchSpy).toHaveBeenCalledExactlyOnceWith(path, expect.objectContaining({
    method: "POST", credentials: "include", body: expect.any(FormData),
  }))
  const formData = fetchSpy.mock.calls[0][1]?.body as FormData
  expect(formData.get("file")).toMatchObject({ name: "boundary.xlsx" })
})
