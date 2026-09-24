import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { McpAccountPicker } from "@/components/admin/mcp-account-picker"
import type { McpCandidate, McpPage } from "@/lib/mcp-tokens"

const mocks = vi.hoisted(() => ({ candidates: vi.fn() }))

vi.mock("@/lib/mcp-tokens", () => ({ listMcpCandidates: mocks.candidates }))

const designer: McpCandidate = {
  id: 2,
  username: "designer",
  display_name: "美工甲",
  department_code: "美工部",
  profiles: ["design"],
}
const finance: McpCandidate = {
  id: 3,
  username: "finance",
  display_name: "财务甲",
  department_code: "财务部",
  profiles: ["finance"],
}
const firstPage: McpPage<McpCandidate> = {
  items: [designer, finance],
  total: 2,
  page: 1,
  page_size: 30,
}

function openPicker() {
  fireEvent.click(screen.getByRole("button", { name: "中台账号" }))
  return screen.getByRole("textbox", { name: "搜索中台账号" })
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.candidates.mockResolvedValue(firstPage)
})

afterEach(cleanup)

describe("MCP account picker", () => {
  it("loads only on expansion and displays names, usernames and departments", async () => {
    render(<McpAccountPicker value={null} onChange={vi.fn()} />)
    expect(mocks.candidates).not.toHaveBeenCalled()
    const search = openPicker()
    expect(search).toHaveFocus()
    expect(
      await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    ).toBeEnabled()
    expect(mocks.candidates).toHaveBeenCalledWith("", 1)
    expect(screen.getByText("共 2 个账号")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "下一页账号" })
    ).not.toBeInTheDocument()
  })

  it("selects an account, collapses the panel and returns keyboard focus", async () => {
    const onChange = vi.fn()
    const view = render(<McpAccountPicker value={null} onChange={onChange} />)
    openPicker()
    fireEvent.click(
      await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    )
    expect(onChange).toHaveBeenCalledWith(designer)
    expect(
      screen.queryByRole("region", { name: "选择中台账号" })
    ).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "中台账号" })).toHaveFocus()
    view.rerender(<McpAccountPicker value={designer} onChange={onChange} />)
    const selected = screen.getByRole("button", { name: "中台账号" })
    expect(selected).toHaveTextContent("美工甲")
    expect(selected).toHaveTextContent("designer")
    expect(selected).toHaveTextContent("美工部")
    expect(screen.getByText("已选择")).toBeInTheDocument()
  })

  it("debounces search, clears it, and always returns to the first page", async () => {
    render(<McpAccountPicker value={null} onChange={vi.fn()} />)
    const search = openPicker()
    await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    fireEvent.change(search, { target: { value: "财" } })
    fireEvent.change(search, { target: { value: " 财务 " } })
    expect(mocks.candidates).toHaveBeenCalledTimes(1)
    await waitFor(() =>
      expect(mocks.candidates).toHaveBeenLastCalledWith("财务", 1)
    )
    expect(mocks.candidates).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByRole("button", { name: "清空账号搜索" }))
    await waitFor(() =>
      expect(mocks.candidates).toHaveBeenLastCalledWith("", 1)
    )
    expect(search).toHaveValue("")
    expect(search).toHaveFocus()
  })

  it("supports all pages without clearing the selected account", async () => {
    const onChange = vi.fn()
    mocks.candidates.mockImplementation((_query: string, page: number) =>
      Promise.resolve({
        items: page === 1 ? [designer] : [finance],
        total: 69,
        page,
        page_size: 30,
      })
    )
    render(<McpAccountPicker value={designer} onChange={onChange} />)
    const search = openPicker()
    await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    expect(screen.getByRole("button", { name: "上一页账号" })).toBeDisabled()
    expect(screen.getByText("1 / 3")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "下一页账号" }))
    await screen.findByRole("radio", { name: "finance · 财务甲 · 财务部" })
    expect(mocks.candidates).toHaveBeenLastCalledWith("", 2)
    expect(screen.getByText("2 / 3")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "中台账号" })).toHaveTextContent(
      "designer"
    )
    fireEvent.click(screen.getByRole("button", { name: "下一页账号" }))
    await waitFor(() => expect(screen.getByText("3 / 3")).toBeInTheDocument())
    expect(screen.getByRole("button", { name: "下一页账号" })).toBeDisabled()
    fireEvent.change(search, { target: { value: "美工" } })
    await waitFor(() =>
      expect(mocks.candidates).toHaveBeenLastCalledWith("美工", 1)
    )
    expect(onChange).not.toHaveBeenCalled()
  })

  it("shows an empty search without clearing the existing selection", async () => {
    mocks.candidates.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 30,
    })
    render(<McpAccountPicker value={designer} onChange={vi.fn()} />)
    const search = openPicker()
    fireEvent.change(search, { target: { value: "不存在的账号" } })
    expect(await screen.findByRole("status")).toHaveTextContent("正在加载账号")
    await screen.findByText("没有找到匹配账号")
    expect(screen.getByRole("button", { name: "中台账号" })).toHaveTextContent(
      "designer"
    )
    expect(screen.queryByRole("radio")).not.toBeInTheDocument()
  })

  it("retries a failed request without enabling stale choices", async () => {
    mocks.candidates
      .mockRejectedValueOnce(new Error("暂时无法加载账号"))
      .mockResolvedValue(firstPage)
    render(<McpAccountPicker value={null} onChange={vi.fn()} />)
    openPicker()
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "暂时无法加载账号"
    )
    expect(screen.queryByRole("radio")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "重新加载账号" }))
    await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(mocks.candidates).toHaveBeenCalledTimes(2)
  })

  it("discards an older search response arriving after the latest result", async () => {
    let resolveOld!: (response: McpPage<McpCandidate>) => void
    mocks.candidates.mockImplementation((query: string) => {
      if (query === "旧搜索")
        return new Promise((resolve) => {
          resolveOld = resolve
        })
      return Promise.resolve(
        query ? { ...firstPage, items: [finance], total: 1 } : firstPage
      )
    })
    render(<McpAccountPicker value={null} onChange={vi.fn()} />)
    const search = openPicker()
    await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    fireEvent.change(search, { target: { value: "旧搜索" } })
    await waitFor(() =>
      expect(mocks.candidates).toHaveBeenLastCalledWith("旧搜索", 1)
    )
    fireEvent.change(search, { target: { value: "finance" } })
    await screen.findByRole("radio", { name: "finance · 财务甲 · 财务部" })
    await act(async () => {
      resolveOld({ ...firstPage, items: [designer], total: 1 })
    })
    expect(
      screen.queryByRole("radio", { name: "designer · 美工甲 · 美工部" })
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole("radio", { name: "finance · 财务甲 · 财务部" })
    ).toBeInTheDocument()
  })

  it("does not select accounts with no permitted query scope", async () => {
    mocks.candidates.mockResolvedValue({
      ...firstPage,
      items: [{ ...designer, profiles: [] }],
    })
    const onChange = vi.fn()
    render(<McpAccountPicker value={null} onChange={onChange} />)
    openPicker()
    const option = await screen.findByRole("radio", {
      name: "designer · 美工甲 · 美工部",
    })
    expect(option).toBeDisabled()
    expect(screen.getByText(/暂无查询范围/)).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it("disables the trigger and open controls while the parent form saves", async () => {
    const onChange = vi.fn()
    const view = render(
      <McpAccountPicker value={designer} onChange={onChange} />
    )
    openPicker()
    await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    view.rerender(
      <McpAccountPicker value={designer} onChange={onChange} disabled />
    )
    expect(screen.getByRole("button", { name: "中台账号" })).toBeDisabled()
    expect(screen.getByRole("textbox", { name: "搜索中台账号" })).toBeDisabled()
    for (const account of screen.getAllByRole("radio"))
      expect(account).toBeDisabled()
  })

  it("supports keyboard entry into results and Escape to collapse", async () => {
    render(<McpAccountPicker value={null} onChange={vi.fn()} />)
    const search = openPicker()
    await screen.findByRole("radio", { name: "designer · 美工甲 · 美工部" })
    fireEvent.keyDown(search, { key: "ArrowDown" })
    const accounts = screen.getByRole("radiogroup", { name: "可选中台账号" })
    expect(within(accounts).getAllByRole("radio")[0]).toHaveFocus()
    fireEvent.keyDown(accounts, { key: "Escape" })
    expect(screen.getByRole("button", { name: "中台账号" })).toHaveAttribute(
      "aria-expanded",
      "false"
    )
    expect(screen.getByRole("button", { name: "中台账号" })).toHaveFocus()
  })
})
