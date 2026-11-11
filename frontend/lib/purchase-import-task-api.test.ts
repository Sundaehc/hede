import { afterEach, expect, test, vi } from "vitest"
import { getPurchaseImportTask, resolveMissingImportTask, submitPurchaseImportTask } from "@/lib/api"

afterEach(() => vi.restoreAllMocks())

test.each(["purchase", "inventory"] as const)("resolves an unreceived %s batch without sending any file", async (operation) => {
  const result = { closed: true, task: { task_id: "a".repeat(32), status: "failed" } }
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify(result)))
  const controller = new AbortController()
  expect(await resolveMissingImportTask("a".repeat(32), operation, controller.signal)).toEqual(result)
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
    `/api/inventory/${operation === "purchase" ? "import-purchase" : "import-template"}/tasks/${"a".repeat(32)}/resolve-missing`,
    expect.objectContaining({ method: "POST", credentials: "include", cache: "no-store", signal: expect.any(AbortSignal) }),
  )
  expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined()
  controller.abort()
  expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true)
})

test("submits purchase parameters once and returns an accepted task without waiting for import", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({
    task_id: "a".repeat(32), status: "running", result: null,
  }), { status: 202 }))
  const file = new File(["excel"], "采购.xlsx")
  const task = await submitPurchaseImportTask({
    taskId: "a".repeat(32), file, document_type: "进货订单", supplier: "工厂",
    warehouse: "", handler: "经手人", summary: "采购", delivery_date: "2026-12-01",
    brand: "ni", preview: true, decisions: { "1": { action: "new", new_summary: "采购补单" } },
  })
  expect(task.status).toBe("running")
  expect(fetchMock).toHaveBeenCalledOnce()
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe("/api/inventory/import-purchase/tasks/" + "a".repeat(32))
  expect(init).toMatchObject({ method: "POST", credentials: "include" })
  const body = init?.body as FormData
  expect(body.get("file")).toBe(file)
  expect(body.get("preview")).toBe("true")
  expect(body.get("delivery_date")).toBe("2026-12-01")
  expect(JSON.parse(String(body.get("decisions")))).toEqual({ "1": { action: "new", new_summary: "采购补单" } })
})

test("queries purchase task without caching and allows cancellation", async () => {
  const controller = new AbortController()
  const fetchMock = vi.spyOn(global, "fetch").mockImplementation((_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true })
  }))
  const pending = getPurchaseImportTask("a".repeat(32), controller.signal)
  expect(fetchMock).toHaveBeenCalledWith("/api/inventory/import-purchase/tasks/" + "a".repeat(32), expect.objectContaining({
    credentials: "include", cache: "no-store", signal: expect.any(AbortSignal),
  }))
  controller.abort()
  await expect(pending).rejects.toMatchObject({ name: "AbortError" })
})
