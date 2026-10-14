import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { UserAdminPage } from "@/components/admin/user-admin-page"

const mocks = vi.hoisted(() => ({
  createAdminUser: vi.fn(),
  hasPermission: () => true,
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role_code: "super_admin" }, hasPermission: mocks.hasPermission }),
}))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", () => ({
  createAdminUser: mocks.createAdminUser,
  updateAdminUser: vi.fn(),
  getAuthOptions: async () => ({
    departments: [{ id: 1, code: "finance", name: "财务部" }],
    roles: [{ id: 1, code: "finance_staff", name: "财务组", department_code: "finance", description: null, permissions: [] }],
  }),
  listAdminUsers: async () => ({
    items: [], total: 0, page: 1, page_size: 20,
    stats: { active: 0, disabled: 0, department_count: 0 },
  }),
}))

beforeEach(() => {
  mocks.createAdminUser.mockReset()
  mocks.createAdminUser.mockResolvedValue({ message: "账号已创建" })
})
afterEach(cleanup)

describe("Create account password visibility", () => {
  it("toggles each password independently without changing values or submitting the form", async () => {
    const actor = userEvent.setup()
    render(<UserAdminPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
    await actor.click(screen.getByRole("button", { name: "创建账号" }))
    const dialog = within(screen.getByRole("dialog", { name: "创建账号" }))
    const password = dialog.getByLabelText("初始密码")
    const confirmation = dialog.getByLabelText("确认密码")
    expect(password).toHaveAttribute("type", "password")
    expect(confirmation).toHaveAttribute("type", "password")
    await actor.type(password, "Test-Password-123")
    await actor.type(confirmation, "Test-Password-123")

    await actor.click(dialog.getByRole("button", { name: "显示初始密码" }))
    expect(password).toHaveAttribute("type", "text")
    expect(confirmation).toHaveAttribute("type", "password")
    expect(dialog.getByRole("button", { name: "隐藏初始密码" })).toHaveAttribute("aria-pressed", "true")

    await actor.click(dialog.getByRole("button", { name: "显示确认密码" }))
    expect(confirmation).toHaveAttribute("type", "text")
    await actor.click(dialog.getByRole("button", { name: "隐藏初始密码" }))
    expect(password).toHaveAttribute("type", "password")
    expect(confirmation).toHaveAttribute("type", "text")

    dialog.getByRole("button", { name: "隐藏确认密码" }).focus()
    await actor.keyboard("{Enter}")
    expect(confirmation).toHaveAttribute("type", "password")
    expect(dialog.getByRole("button", { name: "显示确认密码" })).toHaveAttribute("aria-pressed", "false")
    expect(password).toHaveValue("Test-Password-123")
    expect(confirmation).toHaveValue("Test-Password-123")
    expect(mocks.createAdminUser).not.toHaveBeenCalled()
    expect(dialog.queryByText("账号至少需要 2 个字符")).not.toBeInTheDocument()
  })

  it("resets visibility and password values when reopening the dialog", async () => {
    const actor = userEvent.setup()
    render(<UserAdminPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
    await actor.click(screen.getByRole("button", { name: "创建账号" }))
    const dialog = within(screen.getByRole("dialog", { name: "创建账号" }))
    await actor.type(dialog.getByLabelText("初始密码"), "Test-Password-123")
    await actor.type(dialog.getByLabelText("确认密码"), "Test-Password-123")
    await actor.click(dialog.getByRole("button", { name: "显示初始密码" }))
    await actor.click(dialog.getByRole("button", { name: "显示确认密码" }))
    await actor.click(dialog.getByRole("button", { name: "取消" }))
    await actor.click(screen.getByRole("button", { name: "创建账号" }))

    const reopenedDialog = within(screen.getByRole("dialog", { name: "创建账号" }))
    expect(reopenedDialog.getByLabelText("初始密码")).toHaveAttribute("type", "password")
    expect(reopenedDialog.getByLabelText("确认密码")).toHaveAttribute("type", "password")
    expect(reopenedDialog.getByLabelText("初始密码")).toHaveValue("")
    expect(reopenedDialog.getByLabelText("确认密码")).toHaveValue("")
  })

  it("submits the original password after changing visibility", async () => {
    const actor = userEvent.setup()
    render(<UserAdminPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
    await actor.click(screen.getByRole("button", { name: "创建账号" }))
    const dialog = within(screen.getByRole("dialog", { name: "创建账号" }))
    await actor.type(dialog.getByLabelText("登录账号"), "test.user")
    await actor.type(dialog.getByLabelText("姓名"), "测试用户")
    await actor.type(dialog.getByLabelText("初始密码"), "Test-Password-123")
    await actor.type(dialog.getByLabelText("确认密码"), "Test-Password-123")
    await actor.click(dialog.getByRole("button", { name: "显示初始密码" }))
    await actor.click(dialog.getByRole("button", { name: "显示确认密码" }))
    expect(mocks.createAdminUser).not.toHaveBeenCalled()
    await actor.click(dialog.getByRole("button", { name: "创建账号" }))

    await waitFor(() => expect(mocks.createAdminUser).toHaveBeenCalledExactlyOnceWith({
      username: "test.user",
      display_name: "测试用户",
      department_code: "finance",
      role_code: "finance_staff",
      status: "active",
      password: "Test-Password-123",
    }))
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "创建账号" })).not.toBeInTheDocument())
  })
})
