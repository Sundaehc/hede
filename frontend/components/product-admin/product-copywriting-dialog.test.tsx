import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ProductCopywritingDialog } from "@/components/product-admin/product-copywriting-dialog"
import type { ProductListItem } from "@/lib/types"

const { generate, regenerate } = vi.hoisted(() => ({ generate: vi.fn(), regenerate: vi.fn() }))
vi.mock("@/lib/api", () => ({ getSavedProductCopywriting: generate, regenerateProductCopywriting: regenerate }))

const item = { id: 7, brand: "cbanner_womens", sku: "RM363238D45", product_name: "女休闲鞋", color: "灰色" } as ProductListItem
const content = "【主标题】\n灰色圆头日常穿搭\n【副标题】\n搭扣点缀休闲造型\n【主文案】\n根据真实档案生成的文案\n【卖点】\n鞋面材质：牛剖层皮革\n【图片建议】\n材质细节图\n【风险校对】\n重量信息未提供，待确认"
const copyableContent = "【主标题】\n灰色圆头日常穿搭\n【副标题】\n搭扣点缀休闲造型\n【主文案】\n根据真实档案生成的文案\n【卖点】\n鞋面材质：牛剖层皮革\n【图片建议】\n材质细节图"
const inputPrompt = "你是鞋类电商详情页文案编辑。\n产品名称或款号：【RM363238D45】\n请输出固定六个区块。"
const result = { status: "completed", message: "", input_prompt: inputPrompt, prompt_source: "saved", item: { content, model: "doubao-seed-pro", generated_at: "2026-09-21T10:00:00Z", source_updated_at: "2026-09-21", stale: false, source_sku: "RM363238D45", launch_date: "2026-09-21" } }

beforeEach(() => {
  vi.clearAllMocks()
  generate.mockResolvedValue(result)
  regenerate.mockResolvedValue({ status: "running", message: "已提交重新生成任务，完成后请点击刷新内容查看最新结果。" })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test("opens with loading state and renders all generated sections", async () => {
  let finish: (value: typeof result) => void = () => undefined
  generate.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  expect(screen.getByRole("dialog", { name: "生图提示词" })).toBeInTheDocument()
  expect(screen.getByRole("status")).toHaveTextContent("正在读取已保存的提示词")
  expect(screen.getByRole("button", { name: "复制全部" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "刷新内容" })).toBeDisabled()
  expect(generate).toHaveBeenCalledWith("cbanner_womens", 7)
  finish(result)
  for (const heading of ["主标题", "副标题", "主文案", "卖点", "图片建议", "风险校对"]) {
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument()
  }
  expect(screen.getByText("重量信息未提供，待确认")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "复制全部" })).toBeEnabled()
})

test("shows database read errors without fake content and supports refresh", async () => {
  const user = userEvent.setup()
  generate.mockRejectedValueOnce(new Error("读取数据库失败"))
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("读取数据库失败")
  expect(screen.queryByRole("heading", { name: "主标题" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "刷新内容" }))
  expect(await screen.findByRole("heading", { name: "主标题" })).toBeInTheDocument()
  expect(generate).toHaveBeenLastCalledWith("cbanner_womens", 7)
})

test("refresh retains saved content if the database request fails", async () => {
  const user = userEvent.setup()
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  generate.mockRejectedValueOnce(new Error("请求过于频繁"))
  expect(screen.getByRole("button", { name: "重新生成" })).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "刷新内容" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("下方保留上次读取的内容")
  expect(generate).toHaveBeenLastCalledWith("cbanner_womens", 7)
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
})

test("submits regeneration and keeps the previous content while the job runs", async () => {
  const user = userEvent.setup()
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  await user.click(screen.getByRole("button", { name: "重新生成" }))
  expect(regenerate).toHaveBeenCalledWith("cbanner_womens", 7, inputPrompt)
  expect(await screen.findByRole("status")).toHaveTextContent("已提交重新生成任务")
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "生成中…" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "刷新内容" })).toBeEnabled()
})

test("does not submit a second regeneration while the first request is pending", async () => {
  const user = userEvent.setup()
  let finish: (value: { status: "running"; message: string }) => void = () => undefined
  regenerate.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  const button = screen.getByRole("button", { name: "重新生成" })
  await user.click(button)
  expect(button).toBeDisabled()
  await user.click(button)
  expect(regenerate).toHaveBeenCalledOnce()
  finish({ status: "running", message: "任务已提交" })
  await screen.findByText("任务已提交")
})

test("copies the entire result on HTTPS", async () => {
  const user = userEvent.setup()
  vi.stubGlobal("isSecureContext", true)
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  await user.click(screen.getByRole("button", { name: "复制全部" }))
  expect(writeText).toHaveBeenCalledWith(copyableContent)
  expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument()
})

test("copies on LAN HTTP using an in-dialog fallback", async () => {
  const user = userEvent.setup()
  vi.stubGlobal("isSecureContext", false)
  const execCommand = vi.fn(() => {
    expect(screen.getByRole("dialog").querySelector<HTMLTextAreaElement>("textarea[style]")?.value).toBe(copyableContent)
    return true
  })
  Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand })
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  await user.click(screen.getByRole("button", { name: "复制全部" }))
  expect(execCommand).toHaveBeenCalledWith("copy")
  expect(screen.getByRole("dialog").querySelectorAll("textarea")).toHaveLength(1)
  expect(screen.getByRole("textbox", { name: "生成提示词（可编辑）" })).toHaveValue(inputPrompt)
  expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument()
})

test("failed clipboard access offers manual copying", async () => {
  const user = userEvent.setup()
  vi.stubGlobal("isSecureContext", true)
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"))
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  await user.click(screen.getByRole("button", { name: "复制全部" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("手动复制")
})

test("ignores an old product response after switching to another product", async () => {
  let finishFirst: (value: typeof result) => void = () => undefined
  generate.mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve }))
  const { rerender } = render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  rerender(<ProductCopywritingDialog item={{ ...item, id: 8, sku: "NEW-008" }} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  finishFirst({ ...result, item: { ...result.item, content: "旧商品结果" } })
  await waitFor(() => expect(screen.queryByText("旧商品结果")).not.toBeInTheDocument())
  expect(screen.getByText("NEW-008")).toBeInTheDocument()
})

test("renders model output as text rather than executable HTML and closes with Escape", async () => {
  const user = userEvent.setup()
  const onClose = vi.fn()
  generate.mockResolvedValue({ ...result, item: { ...result.item, content: content + "\n<script>alert('xss')</script>" } })
  render(<ProductCopywritingDialog item={item} onClose={onClose} />)
  await screen.findByRole("heading", { name: "主标题" })
  expect(screen.getByRole("dialog").querySelector("script")).toBeNull()
  expect(screen.getByRole("dialog")).toHaveTextContent("<script>alert('xss')</script>")
  await user.keyboard("{Escape}")
  expect(onClose).toHaveBeenCalledOnce()
})

test.each(["missing", "pending", "running", "failed"])("shows %s database state without automatically generating", async (status) => {
  generate.mockResolvedValue({ status, item: null, message: "暂无已保存内容，请稍后刷新" })
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  expect(await screen.findByText("暂无已保存内容，请稍后刷新")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "复制全部" })).toBeDisabled()
  if (status === "pending" || status === "running") {
    expect(screen.getByRole("button", { name: "生成中…" })).toBeDisabled()
  } else {
    expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled()
  }
  expect(regenerate).not.toHaveBeenCalled()
  expect(generate).toHaveBeenCalledOnce()
})

test("polls only reads after submission and stops when the new content is saved", async () => {
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "重新生成" })) })
  generate.mockResolvedValueOnce({ ...result, status: "running", message: "正在生成" })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
  generate.mockResolvedValueOnce({ ...result, item: { ...result.item, content: "【主标题】\n新生成的文案" } })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByText("新生成的文案")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled()
  const calls = generate.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
  expect(generate).toHaveBeenCalledTimes(calls)
  expect(regenerate).toHaveBeenCalledOnce()
})

test("poll failure preserves content and stops automatic reads until refresh", async () => {
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "重新生成" })) })
  generate.mockRejectedValueOnce(new Error("网络中断，请刷新"))
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByRole("alert")).toHaveTextContent("网络中断")
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
  expect(generate).toHaveBeenCalledTimes(2)
  generate.mockResolvedValueOnce({ ...result, status: "failed", message: "生成失败，保留上一版内容" })
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "刷新内容" })) })
  expect(screen.getByRole("alert")).toHaveTextContent("生成失败")
  expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled()
})

test("ignores regeneration responses after switching products", async () => {
  const user = userEvent.setup()
  let finish: (value: { status: "running"; message: string }) => void = () => undefined
  regenerate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  const { rerender } = render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  await user.click(screen.getByRole("button", { name: "重新生成" }))
  rerender(<ProductCopywritingDialog item={{ ...item, id: 8, sku: "NEW-008" }} onClose={vi.fn()} />)
  await screen.findByRole("button", { name: "重新生成" })
  await act(async () => { finish({ status: "running", message: "旧商品任务" }) })
  expect(screen.queryByText("旧商品任务")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled()
})

test("closing stops polling without cancelling the server task", async () => {
  const user = userEvent.setup()
  const { unmount } = render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  await user.click(screen.getByRole("button", { name: "重新生成" }))
  unmount()
  expect(regenerate).toHaveBeenCalledOnce()
  expect(generate).toHaveBeenCalledOnce()
})

test("shows archived content with a warning when product facts changed", async () => {
  generate.mockResolvedValue({ ...result, item: { ...result.item, stale: true }, message: "商品档案已变化，上版前请核对" })
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("商品档案已变化")
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
  expect(screen.getByText(/数据库已保存/)).toBeInTheDocument()
})

test("shows the saved input prompt and submits exact edits with regeneration", async () => {
  const user = userEvent.setup()
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  const editor = await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })
  expect(editor).toHaveValue(inputPrompt)
  expect(regenerate).not.toHaveBeenCalled()
  const edited = "  修改后的完整提示词\n强调通勤场景  "
  fireEvent.change(editor, { target: { value: edited } })
  expect(screen.getByText("有未提交的修改")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "撤销修改" })).toBeEnabled()
  regenerate.mockResolvedValueOnce({ status: "running", message: "正在重新生成", input_prompt: edited })
  await user.click(screen.getByRole("button", { name: "重新生成" }))
  expect(regenerate).toHaveBeenCalledWith("cbanner_womens", 7, edited)
  expect(editor).toHaveValue(edited)
  expect(editor).toBeDisabled()
  expect(screen.queryByText("有未提交的修改")).not.toBeInTheDocument()
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
})

test("refresh never discards unsubmitted edits and undo restores the saved prompt", async () => {
  const user = userEvent.setup()
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  const editor = await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })
  fireEvent.change(editor, { target: { value: "尚未提交的草稿" } })
  generate.mockResolvedValueOnce({ ...result, input_prompt: "其他人最近提交的提示词" })
  await user.click(screen.getByRole("button", { name: "刷新内容" }))
  await waitFor(() => expect(editor).toBeEnabled())
  expect(editor).toHaveValue("尚未提交的草稿")
  expect(regenerate).not.toHaveBeenCalled()
  await user.click(screen.getByRole("button", { name: "撤销修改" }))
  expect(editor).toHaveValue("其他人最近提交的提示词")
  expect(screen.queryByText("有未提交的修改")).not.toBeInTheDocument()
})

test.each(["", " \n\t ", "字".repeat(30_001)])("invalid edited input disables generation (%#)", async (invalid) => {
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  const editor = await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })
  fireEvent.change(editor, { target: { value: invalid } })
  expect(editor).toHaveAttribute("aria-invalid", "true")
  expect(screen.getByRole("button", { name: "重新生成" })).toBeDisabled()
  expect(regenerate).not.toHaveBeenCalled()
})

test("failed submission keeps edits and old output ready for retry", async () => {
  const user = userEvent.setup()
  regenerate.mockRejectedValueOnce(new Error("请求提交失败"))
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  const editor = await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })
  fireEvent.change(editor, { target: { value: "待重试草稿" } })
  await user.click(screen.getByRole("button", { name: "重新生成" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("请求提交失败")
  expect(editor).toHaveValue("待重试草稿")
  expect(editor).toBeEnabled()
  expect(screen.getByText("有未提交的修改")).toBeInTheDocument()
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
})

test("switching product resets unsent edits without leaking the previous prompt", async () => {
  const { rerender } = render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  const editor = await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })
  fireEvent.change(editor, { target: { value: "旧商品草稿" } })
  generate.mockResolvedValueOnce({ ...result, input_prompt: "新商品提示词" })
  rerender(<ProductCopywritingDialog item={{ ...item, id: 8 }} onClose={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole("textbox", { name: "生成提示词（可编辑）" })).toHaveValue("新商品提示词"))
  expect(screen.queryByText("有未提交的修改")).not.toBeInTheDocument()
})

test("labels archive fallback instead of claiming it was the historical input", async () => {
  generate.mockResolvedValue({ ...result, prompt_source: "archive" })
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  expect(await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })).toHaveValue(inputPrompt)
  expect(screen.getByText(/不代表历史生成输入/)).toBeInTheDocument()
  expect(screen.getByText("灰色圆头日常穿搭")).toBeInTheDocument()
})

test("poll completion keeps the submitted prompt and allows further edits", async () => {
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  const editor = await screen.findByRole("textbox", { name: "生成提示词（可编辑）" })
  const edited = "新的完整提示词"
  fireEvent.change(editor, { target: { value: edited } })
  regenerate.mockResolvedValueOnce({ status: "running", message: "生成中", input_prompt: edited })
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "重新生成" })) })
  generate.mockResolvedValueOnce({ ...result, input_prompt: edited, item: { ...result.item, content: "【主标题】\n编辑后的新文案" } })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(editor).toHaveValue(edited)
  expect(editor).toBeEnabled()
  expect(screen.getByText("编辑后的新文案")).toBeInTheDocument()
  expect(screen.queryByText("有未提交的修改")).not.toBeInTheDocument()
  fireEvent.change(editor, { target: { value: "下一次草稿" } })
  await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
  expect(editor).toHaveValue("下一次草稿")
  expect(generate).toHaveBeenCalledTimes(2)
})

test("older backend responses still show content and use legacy regeneration", async () => {
  const user = userEvent.setup()
  generate.mockResolvedValue({ status: result.status, message: result.message, item: result.item })
  render(<ProductCopywritingDialog item={item} onClose={vi.fn()} />)
  await screen.findByRole("heading", { name: "主标题" })
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "重新生成" }))
  expect(regenerate).toHaveBeenCalledWith("cbanner_womens", 7)
})
