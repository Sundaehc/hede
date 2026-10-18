import { afterEach, expect, test, vi } from "vitest"

import {
  getInventoryTemplateTask,
  submitInventoryTemplateTask,
} from "@/lib/api"

const taskId = "a".repeat(32)
const task = {
  task_id: taskId,
  filename: "单据.xlsx",
  status: "queued",
  result: null,
  error: null,
  error_status: null,
}

afterEach(() => vi.restoreAllMocks())

test("submits a stable batch ID with the file and decisions", async () => {
  const fetchSpy = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(task), { status: 202 }))
  const decisions = { one: { action: "skip" as const } }
  await expect(
    submitInventoryTemplateTask({
      taskId,
      file: new File(["excel"], "单据.xlsx"),
      brand: "ni",
      decisions,
    })
  ).resolves.toEqual(task)
  expect(fetchSpy).toHaveBeenCalledExactlyOnceWith(
    "/api/inventory/import-template/tasks/" + taskId,
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      signal: expect.any(AbortSignal),
    })
  )
  const data = fetchSpy.mock.calls[0][1]?.body as FormData
  expect(data.get("brand")).toBe("ni")
  expect(data.get("decisions")).toBe(JSON.stringify(decisions))
})

test("queries durable status without a cache and supports cancellation", async () => {
  const fetchSpy = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(task)))
  const controller = new AbortController()
  await expect(
    getInventoryTemplateTask(taskId, controller.signal)
  ).resolves.toEqual(task)
  expect(fetchSpy).toHaveBeenCalledWith(
    "/api/inventory/import-template/tasks/" + taskId,
    expect.objectContaining({ cache: "no-store", credentials: "include" })
  )
  const signal = fetchSpy.mock.calls[0][1]?.signal
  controller.abort()
  expect(signal?.aborted).toBe(true)
})

test("preserves a missing batch response as an error instead of assuming success", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "未找到该导入批次" }), {
      status: 404,
    })
  )
  await expect(getInventoryTemplateTask(taskId)).rejects.toMatchObject({
    status: 404,
    message: "未找到该导入批次",
  })
})
