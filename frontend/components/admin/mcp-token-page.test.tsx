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
  audit: vi.fn(),
  copy: vi.fn(),
  legacyCopy: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => mocks.auth,
}))
vi.mock("@/lib/mcp-tokens", () => ({
  listMcpTokens: mocks.list,
  listMcpCandidates: mocks.candidates,
  issueMcpToken: mocks.issue,
  listMcpTokenAudit: mocks.audit,
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
  await waitFor(() => expect(screen.getByLabelText("中台账号")).toBeEnabled())
}

async function selectAccount(username = "designer") {
  fireEvent.click(screen.getByRole("button", { name: "中台账号" }))
  fireEvent.click(await screen.findByRole("radio", { name: new RegExp(`^${username} ·`) }))
}

async function issueAndOpenSecret() {
  await openCreate()
  await selectAccount()
  fireEvent.change(screen.getByLabelText("用途备注"), { target: { value: "办公电脑" } })
  fireEvent.click(screen.getByRole("button", { name: "确认签发" }))
  return await screen.findByLabelText<HTMLTextAreaElement>("新签发的 Token")
}

const originalExecCommand = Object.getOwnPropertyDescriptor(document, "execCommand")

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
  mocks.audit.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, details_available: true })
  mocks.copy.mockResolvedValue(undefined)
  mocks.legacyCopy.mockReturnValue(false)
  Object.defineProperty(document, "execCommand", { configurable: true, value: mocks.legacyCopy })
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: mocks.copy },
  })
})

afterEach(() => {
  cleanup()
  if (originalExecCommand) Object.defineProperty(document, "execCommand", originalExecCommand)
  else Reflect.deleteProperty(document, "execCommand")
})

describe("MCP token administration", () => {
  it("opens per-token query history with SQL and product identifiers", async () => {
    mocks.list.mockResolvedValue({ items: [item], total: 1, page: 1, page_size: 20 })
    mocks.audit.mockResolvedValue({
      items: [{
        id: 3,
        request_id: "request-1234567890",
        token_id: 12,
        user_id: 2,
        tool: "query_readonly",
        status: "completed",
        row_count: 1,
        elapsed_ms: 18,
        created_at: "2026-09-22T10:01:00Z",
        datasets: ["products"],
        query_sql: "SELECT sku, product_name FROM products WHERE sku=:sku",
        query_params: { sku: { type: "str", length: 10 } },
        result_summary: {
          columns: ["sku", "product_name"],
          rows: [["QT653891S73", "测试商品"]],
          truncated: false,
        },
      }],
      total: 1,
      page: 1,
      page_size: 20,
      details_available: true,
    })
    render(<McpTokenPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: /查询.*记录/ })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: /查询.*记录/ }))
    expect(await screen.findByRole("dialog", { name: "Token 查询记录" })).toBeInTheDocument()
    expect(mocks.audit).toHaveBeenCalledWith(12, 1)
    fireEvent.click(screen.getByText("查看查询明细"))
    expect(screen.getByText("SELECT sku, product_name FROM products WHERE sku=:sku")).toBeInTheDocument()
    expect(screen.getByText("QT653891S73")).toBeInTheDocument()
    expect(screen.getByText("测试商品")).toBeInTheDocument()
  })

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
    await selectAccount()
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
    await selectAccount()
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
    await selectAccount()
    expect(screen.getByLabelText("查询范围")).toHaveValue("design")
    await selectAccount("finance")
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
    await selectAccount()
    fireEvent.change(screen.getByLabelText("用途备注"), {
      target: { value: "办公电脑" },
    })
    fireEvent.click(screen.getByRole("button", { name: "确认签发" }))
    fireEvent.click(await screen.findByRole("button", { name: "复制 Token" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("手动复制")
    expect(screen.getByLabelText("新签发的 Token")).toHaveValue(
      "hmcp_synthetic-test-secret"
    )
    const textarea = screen.getByLabelText<HTMLTextAreaElement>("新签发的 Token")
    expect(textarea).toHaveFocus()
    expect(textarea.selectionEnd - textarea.selectionStart).toBe(textarea.value.length)
    expect(screen.queryByRole("button", { name: "已复制" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "全选 Token" })).toBeEnabled()
  })

  it.each(["missing", "rejected"])("copies using the displayed textarea when clipboard is %s", async (mode) => {
    if (mode === "missing") Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined })
    else mocks.copy.mockRejectedValue(new Error("denied"))
    mocks.legacyCopy.mockImplementation(() => {
      const textarea = screen.getByLabelText<HTMLTextAreaElement>("新签发的 Token")
      expect(textarea).toHaveFocus()
      expect(textarea.value.slice(textarea.selectionStart, textarea.selectionEnd)).toBe("hmcp_synthetic-test-secret")
      return true
    })
    render(<McpTokenPage />)
    await issueAndOpenSecret()
    fireEvent.click(screen.getByRole("button", { name: "复制 Token" }))
    await screen.findByRole("button", { name: "已复制" })
    expect(mocks.legacyCopy).toHaveBeenCalledExactlyOnceWith("copy")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(mocks.issue).toHaveBeenCalledTimes(1)
    if (mode === "missing") expect(mocks.copy).not.toHaveBeenCalled()
  })

  it("lets users select the whole token without attempting to copy or closing the dialog", async () => {
    render(<McpTokenPage />)
    const textarea = await issueAndOpenSecret()
    textarea.setSelectionRange(3, 4)
    fireEvent.click(screen.getByRole("button", { name: "全选 Token" }))
    expect(textarea).toHaveFocus()
    expect(textarea.selectionStart).toBe(0)
    expect(textarea.selectionEnd).toBe(textarea.value.length)
    expect(mocks.copy).not.toHaveBeenCalled()
    expect(mocks.legacyCopy).not.toHaveBeenCalled()
    expect(screen.getByRole("dialog", { name: "Token 已签发，请立即保存" })).toBeInTheDocument()
  })

  it("allows retry after copy failure and clears the manual-copy message", async () => {
    mocks.copy.mockRejectedValue(new Error("denied"))
    render(<McpTokenPage />)
    await issueAndOpenSecret()
    fireEvent.click(screen.getByRole("button", { name: "复制 Token" }))
    await screen.findByRole("alert")
    mocks.legacyCopy.mockReturnValue(true)
    fireEvent.click(screen.getByRole("button", { name: "复制 Token" }))
    await screen.findByRole("button", { name: "已复制" })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("ignores repeated clicks and a copy result arriving after the dialog closes", async () => {
    let resolveCopy!: () => void
    mocks.copy.mockReturnValue(new Promise<void>((resolve) => { resolveCopy = resolve }))
    render(<McpTokenPage />)
    await issueAndOpenSecret()
    fireEvent.click(screen.getByRole("button", { name: "复制 Token" }))
    expect(screen.getByRole("button", { name: "正在复制…" })).toBeDisabled()
    fireEvent.click(screen.getByRole("button", { name: "正在复制…" }))
    expect(mocks.copy).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole("button", { name: "我已保存，关闭" }))
    await issueAndOpenSecret()
    await act(async () => { resolveCopy() })
    expect(screen.getByRole("button", { name: "复制 Token" })).toBeEnabled()
    expect(screen.queryByRole("button", { name: "已复制" })).not.toBeInTheDocument()
  })

  it("does not copy from a closed dialog after administrator access is lost", async () => {
    let rejectCopy!: (error: Error) => void
    mocks.copy.mockReturnValue(new Promise((_resolve, reject) => { rejectCopy = reject }))
    const view = render(<McpTokenPage />)
    await issueAndOpenSecret()
    fireEvent.click(screen.getByRole("button", { name: "复制 Token" }))
    mocks.auth.user.role_code = "staff"
    view.rerender(<McpTokenPage />)
    await act(async () => { rejectCopy(new Error("denied")) })
    expect(mocks.legacyCopy).not.toHaveBeenCalled()
    expect(screen.queryByLabelText("新签发的 Token")).not.toBeInTheDocument()
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
    await selectAccount()
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
    await selectAccount()
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

  it("removes the requested explanatory paragraph without changing expiry controls", async () => {
    render(<McpTokenPage />)
    await openCreate()
    expect(screen.queryByText(/默认有效期为 30 天/)).not.toBeInTheDocument()
    expect(screen.queryByText(/查询结果会进入员工使用的模型上下文/)).not.toBeInTheDocument()
    expect(screen.queryByText(/rathole 隧道密钥/)).not.toBeInTheDocument()
    expect(screen.getByLabelText("有效期（天）")).toHaveValue(30)
    expect(screen.getByRole("checkbox", { name: /永久有效/ })).not.toBeChecked()
  })

  it("omits the explanatory cards while keeping the token list and actions", async () => {
    render(<McpTokenPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "签发 Token" })).toBeEnabled())
    expect(screen.queryByRole("region", { name: "凭证使用说明" })).not.toBeInTheDocument()
    expect(screen.queryByText("一人一证，随时撤销")).not.toBeInTheDocument()
    expect(screen.queryByText("商品档案为基础")).not.toBeInTheDocument()
    expect(screen.queryByText("DESIGN")).not.toBeInTheDocument()
    expect(screen.getByRole("region", { name: "已签发凭证" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "刷新" })).toBeEnabled()
  })

  it("closes the account picker with Escape without closing the issuance dialog", async () => {
    render(<McpTokenPage />)
    await openCreate()
    fireEvent.click(screen.getByRole("button", { name: "中台账号" }))
    fireEvent.keyDown(screen.getByRole("textbox", { name: "搜索中台账号" }), { key: "Escape" })
    expect(screen.queryByRole("region", { name: "选择中台账号" })).not.toBeInTheDocument()
    expect(screen.getByRole("dialog", { name: "签发个人 Token" })).toBeInTheDocument()
    expect(mocks.issue).not.toHaveBeenCalled()
  })
})
