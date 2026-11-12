import { afterEach, beforeEach, expect, test, vi } from "vitest"
import {
  createDetail, deleteProduct, getInventoryTemplateTask, getPurchaseImportTask, importProducts,
  listInventorySelectionIds, listProductSelectionIds, previewInventoryTemplate, previewPurchaseInventory,
  replaceDetailsFromExcel, resolveMissingImportTask, submitPurchaseImportTask, updateInventoryRecord, updateProduct, updateSizeGroup,
} from "@/lib/api"
import { publishBusinessDataChange } from "@/lib/business-data-sync"

vi.mock("@/lib/business-data-sync", async () => ({
  ...(await vi.importActual<typeof import("@/lib/business-data-sync")>("@/lib/business-data-sync")),
  publishBusinessDataChange: vi.fn(),
  // Keep the real route classifier, observing only the transport output.
}))

let messages: unknown[]
beforeEach(() => {
  messages = []
  vi.stubGlobal("BroadcastChannel", class {
    postMessage(value: unknown) { messages.push(value) }
    close() {}
  })
  vi.spyOn(global, "fetch").mockImplementation(async () => new Response(JSON.stringify({ item: { id: 1 }, items: [], total: 0 })))
  vi.mocked(publishBusinessDataChange).mockClear()
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

test("notifies after successful product, document, detail and size rule mutations", async () => {
  await updateProduct("cbanner_womens", 1, { product_name: "新名称" })
  await deleteProduct("cbanner_womens", 2)
  await updateInventoryRecord(1, { summary: "新摘要" })
  await createDetail(1, { product_code: "ABC", quantity: "1" })
  await updateSizeGroup(1, { name: "测试尺码", items: [] })
  expect(messages).toHaveLength(5)
  expect(messages).toEqual([
    expect.objectContaining({ resources: ["products"] }), expect.objectContaining({ resources: ["products"] }),
    expect.objectContaining({ resources: ["inventory"] }), expect.objectContaining({ resources: ["inventory"] }),
    expect.objectContaining({ resources: ["reference-data", "products", "inventory"] }),
  ])
})

test("selection requests, prechecks and rejected saves never publish changes", async () => {
  await listProductSelectionIds({ brand: "all" })
  await listInventorySelectionIds({})
  const file = new File(["excel"], "import.xlsx")
  await previewInventoryTemplate(file)
  await previewPurchaseInventory({ file, document_type: "进货订单", supplier: "工厂", warehouse: "", handler: "测试", summary: "采购" })
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "校验失败" }), { status: 400 }))
  await expect(updateInventoryRecord(1, {})).rejects.toThrow("校验失败")
  expect(messages).toHaveLength(0)
  expect(publishBusinessDataChange).not.toHaveBeenCalled()
})

test("file imports publish only after successful completion", async () => {
  const file = new File(["excel"], "import.xlsx")
  await importProducts("cbanner_womens", file)
  await replaceDetailsFromExcel({ documentId: 1, file })
  expect(publishBusinessDataChange).toHaveBeenNthCalledWith(1, ["products", "inventory"])
  expect(publishBusinessDataChange).toHaveBeenNthCalledWith(2, ["inventory"])
})

test("background precheck and running tasks stay silent, successful writes notify once per task", async () => {
  const task = { task_id: "sync-task", status: "running", result: null }
  const respond = (value: object) => vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(value)))
  respond(task)
  await submitPurchaseImportTask({ taskId: task.task_id, file: new File(["excel"], "a.xlsx"), document_type: "进货订单", supplier: "工厂", warehouse: "", handler: "测试", summary: "采购" })
  respond({ ...task, status: "succeeded", preview: { total: 1 } })
  await getPurchaseImportTask("preview-task")
  expect(publishBusinessDataChange).not.toHaveBeenCalled()
  respond({ ...task, status: "succeeded", result: { created: 1 } })
  await getPurchaseImportTask(task.task_id)
  respond({ ...task, status: "succeeded", result: { created: 1 } })
  await getPurchaseImportTask(task.task_id)
  expect(publishBusinessDataChange).toHaveBeenCalledTimes(1)
  respond({ ...task, task_id: "template-sync-task", status: "succeeded", result: { created: 1 } })
  await getInventoryTemplateTask("template-sync-task")
  expect(publishBusinessDataChange).toHaveBeenCalledTimes(2)
})

test("recovering a committed import also notifies other lists, without repeating the notification", async () => {
  const task = { task_id: "recovered-success-task", status: "succeeded", result: { created: 1 } }
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ closed: false, task })))
  await resolveMissingImportTask(task.task_id, "purchase")
  expect(publishBusinessDataChange).toHaveBeenCalledExactlyOnceWith(["inventory"])
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(task)))
  await getPurchaseImportTask(task.task_id)
  expect(publishBusinessDataChange).toHaveBeenCalledTimes(1)
})
