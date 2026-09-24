import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { McpTokenPage } from "@/components/admin/mcp-token-page"

const mocks = vi.hoisted(() => ({
  auth: {
    user: { id: 1, role_code: "super_admin", status: "active" },
    loading: false,
    hasPermission: vi.fn(),
  },
  list: vi.fn(),
  candidates: vi.fn(),
  issue: vi.fn(),
  revoke: vi.fn(),
  copy: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => mocks.auth,
}))
vi.mock("@/lib/mcp-tokens", () => ({
  listMcpTokens: mocks.list,
  listMcpCandidates: mocks.candidates,
  issueMcpToken: mocks.issue,
  revokeMcpToken: mocks.revoke,
}))

const item = {
  id: 12,
  user_id: 2,
  username: "designer",
  display_name: "美工甲",
  department_code: "美工部",
  label: "办公电脑",
  profile: "design",
  state: "active",
  created_at: "2026-09-22T10:00:00Z",
  expires_at: "2026-10-22T10:00:00Z",
  revoked_at: null,
}

async function openCreate() {
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "签发 Token" })).toBeEnabled()
  )
  fireEvent.click(screen.getByRole("button", { name: "签发 Token" }))
  await screen.findByRole("option", { name: "designer · 美工甲 · 美工部" })
  await waitFor(() => expect(screen.getByLabelText("中台账号")).toBeEnabled())
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.auth.user = { id: 1, role_code: "super_admin", status: "active" }
  mocks.auth.loading = false
  mocks.auth.hasPermission.mockReturnValue(true)
  mocks.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  mocks.candidates.mockResolvedValue({
    items: [
      {
        id: 2,
        username: "designer",
        display_name: "美工甲",
        department_code: "美工部",
        profiles: ["design"],
      },
      {
        id: 3,
        username: "finance",
        display_name: "财务甲",
        department_code: "财务部",
        profiles: ["finance"],
      },
    ],
    total: 2,
    page: 1,
    page_size: 30,
  })
  mocks.issue.mockResolvedValue({ token: "hmcp_synthetic-test-secret", item })
  mocks.revoke.mockResolvedValue({ changed: true, message: "凭证已撤销" })
  mocks.copy.mockResolvedValue(undefined)
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: mocks.copy },
  })
})

afterEach(cleanup)

describe("MCP token administration", () => {
  it("does not fetch credentials for an unauthorized user", () => {
    mocks.auth.user.role_code = "staff"
    render(<McpTokenPage />)
    expect(
      screen.getByText("仅超级管理员可以管理 MCP Token。")
    ).toBeInTheDocument()
    expect(mocks.list).not.toHaveBeenCalled()
    expect(mocks.candidates).not.toHaveBeenCalled()
  })

  it("does not fetch credentials while session authentication is loading", () => {
    mocks.auth.loading = true
    render(<McpTokenPage />)
    expect(screen.getByRole("status")).toHaveTextContent("正在确认管理权限")
    expect(mocks.list).not.toHaveBeenCalled()
  })

  it("issues once, copies only the secret, and removes it after closing", async () => {
    render(<McpTokenPage />)
    await openCreate()
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "2" },
    })
    fireEvent.change(screen.getByLabelText("查询范围"), {
      target: { value: "design" },
    })
    fireEvent.change(screen.getByLabelText("用途备注"), {
      target: { value: "办公电脑" },
    })
    fireEvent.click(screen.getByRole("button", { name: "确认签发" }))
    await screen.findByRole("dialog", { name: "Token 已签发，请立即保存" })
    expect(mocks.issue).toHaveBeenCalledWith({
      user_id: 2,
      profile: "design",
      days: 30,
      label: "办公电脑",
    })
    expect(mocks.issue).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText("新签发的 Token")).toHaveValue(
      "hmcp_synthetic-test-secret"
    )
    fireEvent.click(screen.getByRole("button", { name: "复制 Token" }))
    await screen.findByRole("button", { name: "已复制" })
    expect(mocks.copy).toHaveBeenCalledWith("hmcp_synthetic-test-secret")
    fireEvent.click(screen.getByRole("button", { name: "我已保存，关闭" }))
    expect(screen.queryByLabelText("新签发的 Token")).not.toBeInTheDocument()
    await openCreate()
    expect(screen.queryByLabelText("新签发的 Token")).not.toBeInTheDocument()
  })

  it("issues a permanent token only when the explicit option is selected", async () => {
    render(<McpTokenPage />)
    await openCreate()
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "2" },
    })
    fireEvent.click(screen.getByRole("checkbox", { name: /永久有效/ }))
    expect(screen.getByLabelText("有效期（天）")).toBeDisabled()
    fireEvent.change(screen.getByLabelText("用途备注"), {
      target: { value: "长期办公电脑" },
    })
    fireEvent.click(screen.getByRole("button", { name: "确认签发" }))
    await screen.findByRole("dialog", { name: "Token 已签发，请立即保存" })
    expect(mocks.issue).toHaveBeenCalledWith({
      user_id: 2,
      profile: "design",
      days: null,
      label: "长期办公电脑",
    })
  })

  it("limits design scope to eligible users and resets scope when changing user", async () => {
    render(<McpTokenPage />)
    await openCreate()
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "2" },
    })
    expect(screen.getByLabelText("查询范围")).toHaveValue("design")
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "3" },
    })
    expect(screen.getByLabelText("查询范围")).toHaveValue("finance")
    expect(
      within(screen.getByLabelText("查询范围")).queryByRole("option", {
        name: "商品档案 + 美工文案",
      })
    ).not.toBeInTheDocument()
  })

  it("requires confirmation before revoking and reloads the records", async () => {
    mocks.list.mockResolvedValue({
      items: [item],
      total: 1,
      page: 1,
      page_size: 20,
    })
    render(<McpTokenPage />)
    fireEvent.click(
      await screen.findByRole("button", { name: "撤销 办公电脑" })
    )
    expect(mocks.revoke).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "确认撤销" }))
    await screen.findByRole("status")
    expect(mocks.revoke).toHaveBeenCalledWith(12)
    expect(mocks.list).toHaveBeenCalledTimes(2)
  })

  it("shows a manual-copy fallback if clipboard access fails", async () => {
    mocks.copy.mockRejectedValue(new Error("insecure context"))
    render(<McpTokenPage />)
    await openCreate()
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "2" },
    })
    fireEvent.change(screen.getByLabelText("用途备注"), {
      target: { value: "办公电脑" },
    })
    fireEvent.click(screen.getByRole("button", { name: "确认签发" }))
    fireEvent.click(await screen.findByRole("button", { name: "复制 Token" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("手动复制")
    expect(screen.getByLabelText("新签发的 Token")).toHaveValue(
      "hmcp_synthetic-test-secret"
    )
  })

  it("prevents duplicate submissions and closing the form during issuance", async () => {
    let resolveIssue!: (value: unknown) => void
    mocks.issue.mockReturnValue(
      new Promise((resolve) => {
        resolveIssue = resolve
      })
    )
    render(<McpTokenPage />)
    await openCreate()
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "2" },
    })
    fireEvent.change(screen.getByLabelText("用途备注"), {
      target: { value: "办公电脑" },
    })
    const form = screen
      .getByRole("button", { name: "确认签发" })
      .closest("form")!
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(mocks.issue).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled()
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    resolveIssue({ token: "hmcp_synthetic-test-secret", item })
    await screen.findByLabelText("新签发的 Token")
  })

  it("removes the secret if administrator permissions change", async () => {
    const view = render(<McpTokenPage />)
    await openCreate()
    fireEvent.change(screen.getByLabelText("中台账号"), {
      target: { value: "2" },
    })
    fireEvent.change(screen.getByLabelText("用途备注"), {
      target: { value: "办公电脑" },
    })
    fireEvent.click(screen.getByRole("button", { name: "确认签发" }))
    await screen.findByLabelText("新签发的 Token")
    mocks.auth.user.role_code = "staff"
    view.rerender(<McpTokenPage />)
    expect(screen.queryByLabelText("新签发的 Token")).not.toBeInTheDocument()
  })

  it("reports initialization errors without enabling issuance", async () => {
    mocks.list.mockRejectedValue(new Error("MCP尚未初始化"))
    render(<McpTokenPage />)
    expect(await screen.findByRole("alert")).toHaveTextContent("MCP尚未初始化")
    expect(screen.getByRole("button", { name: "签发 Token" })).toBeDisabled()
  })
})
