import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { UserAdminPage } from "@/components/admin/user-admin-page"
import type { AuthUser } from "@/lib/types"

const mocks = vi.hoisted(() => ({
  listUsers: vi.fn(),
  updateUser: vi.fn(),
  hasPermission: () => true,
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role_code: "super_admin" }, hasPermission: mocks.hasPermission }),
}))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/lib/api", () => ({
  createAdminUser: vi.fn(),
  updateAdminUser: mocks.updateUser,
  listAdminUsers: mocks.listUsers,
  getAuthOptions: async () => ({
    departments: [{ id: 1, code: "ops", name: "运营部" }, { id: 2, code: "finance", name: "财务部" }],
    roles: [
      { id: 1, code: "super_admin", name: "超级管理员", department_code: null, description: "系统全部权限", permissions: [] },
      { id: 2, code: "ops_staff", name: "运营组", department_code: "ops", description: "维护商品档案，查看和导出商品档案、精细表及采购单", permissions: [] },
      { id: 3, code: "finance_staff", name: "财务组", department_code: "finance", description: "管理经营历程和采购单", permissions: [] },
    ],
  }),
}))

const users: AuthUser[] = [
  { id: 1, username: "chen", display_name: "陈杰", department_code: "ops", department_name: "运营部", role_code: "ops_staff", role_name: "运营组", status: "active", permissions: [] },
  { id: 2, username: "zheng", display_name: "郑理允", department_code: "finance", department_name: "财务部", role_code: "finance_staff", role_name: "财务组", status: "disabled", permissions: [] },
]

beforeEach(() => {
  vi.resetAllMocks()
  mocks.listUsers.mockResolvedValue({
    items: users,
    total: users.length,
    page: 1,
    page_size: 20,
    stats: { active: 1, disabled: 1, department_count: 2 },
  })
  mocks.updateUser.mockImplementation(async (id, patch) => ({ item: { ...users.find((user) => user.id === id), ...patch } }))
})

afterEach(cleanup)

async function openTable() {
  render(<UserAdminPage />)
  await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
  return within(screen.getByRole("table", { name: "系统账号列表" }))
}

test("uses compact editable rows, a single status field and fixed actions", async () => {
  const table = await openTable()
  const name = table.getByRole("textbox", { name: "chen的姓名" })
  expect(name).toHaveClass("h-8", "shadow-none")
  expect(name.closest("td")).toHaveClass("align-middle", "py-2.5")
  expect(table.getByRole("combobox", { name: "chen的状态" })).toHaveValue("active")
  expect(table.getByRole("combobox", { name: "zheng的状态" })).toHaveValue("disabled")
  expect(table.queryByText("已同步")).not.toBeInTheDocument()
  const save = table.getByRole("button", { name: "保存账号 chen" })
  expect(save).toBeDisabled()
  expect(save).toHaveTextContent("已保存")
  expect(save.closest("td")).toHaveClass("sticky", "right-0")
  expect(screen.getByRole("heading", { name: "用户管理" }).closest(".app-content")).not.toHaveClass("min-w-[760px]")
})

test("shows full role descriptions on demand without making rows taller", async () => {
  const actor = userEvent.setup()
  const table = await openTable()
  expect(screen.queryByText("维护商品档案，查看和导出商品档案、精细表及采购单")).not.toBeInTheDocument()
  await actor.click(table.getByRole("button", { name: "查看 chen 的角色权限" }))
  const description = screen.getByRole("dialog", { name: "角色权限说明" })
  expect(description).toHaveTextContent("运营组")
  expect(description).toHaveTextContent("维护商品档案，查看和导出商品档案、精细表及采购单")
  await actor.keyboard("{Escape}")
  expect(screen.queryByRole("dialog", { name: "角色权限说明" })).not.toBeInTheDocument()
  expect(mocks.updateUser).not.toHaveBeenCalled()
})

test("highlights changed rows and undo restores only the selected account", async () => {
  const actor = userEvent.setup()
  const table = await openTable()
  const firstName = table.getByRole("textbox", { name: "chen的姓名" })
  const secondName = table.getByRole("textbox", { name: "zheng的姓名" })
  await actor.type(firstName, "改")
  await actor.type(secondName, "改")
  expect(screen.getByRole("status")).toHaveTextContent("当前页有 2 个账号待保存")
  expect(firstName.closest("tr")).toHaveAttribute("data-dirty", "true")
  expect(table.getByRole("button", { name: "保存账号 chen" })).toBeEnabled()
  await actor.click(table.getByRole("button", { name: "撤销 chen 的修改" }))
  expect(firstName).toHaveValue("陈杰")
  expect(secondName).toHaveValue("郑理允改")
  expect(firstName.closest("tr")).not.toHaveAttribute("data-dirty")
  expect(screen.getByRole("status")).toHaveTextContent("当前页有 1 个账号待保存")
  expect(mocks.updateUser).not.toHaveBeenCalled()
})

test("toggles an existing account password without changing its value or auto-saving", async () => {
  const actor = userEvent.setup()
  const table = await openTable()
  const password = table.getByLabelText("chen的新密码")
  expect(password).toHaveAttribute("type", "password")
  expect(password).toHaveAttribute("autocomplete", "new-password")
  await actor.type(password, "New-Password-123")
  await actor.click(table.getByRole("button", { name: "显示 chen 的新密码" }))
  expect(password).toHaveAttribute("type", "text")
  expect(password).toHaveValue("New-Password-123")
  await actor.click(table.getByRole("button", { name: "隐藏 chen 的新密码" }))
  expect(password).toHaveAttribute("type", "password")
  expect(table.getByLabelText("zheng的新密码")).toHaveAttribute("type", "password")
  expect(mocks.updateUser).not.toHaveBeenCalled()
  await actor.click(table.getByRole("button", { name: "撤销 chen 的修改" }))
  expect(password).toHaveValue("")
})

test("saves the row fields and excludes an unchanged password", async () => {
  const actor = userEvent.setup()
  const table = await openTable()
  const name = table.getByRole("textbox", { name: "chen的姓名" })
  await actor.clear(name)
  await actor.type(name, "陈杰新")
  await actor.selectOptions(table.getByRole("combobox", { name: "chen的状态" }), "disabled")
  await actor.click(table.getByRole("button", { name: "保存账号 chen" }))
  await waitFor(() => expect(mocks.updateUser).toHaveBeenCalledExactlyOnceWith(1, {
    display_name: "陈杰新", department_code: "ops", role_code: "ops_staff", status: "disabled",
  }))
  await screen.findByText("用户已更新")
  expect(table.getByRole("button", { name: "保存账号 chen" })).toBeDisabled()
  expect(screen.queryByRole("status")).not.toBeInTheDocument()
})

test("keeps the existing department and role linkage while showing the updated permission description", async () => {
  const actor = userEvent.setup()
  const table = await openTable()
  await actor.selectOptions(table.getByRole("combobox", { name: "chen的部门" }), "finance")
  const role = table.getByRole("combobox", { name: "chen的角色" })
  expect(within(role).queryByRole("option", { name: "运营组" })).not.toBeInTheDocument()
  await actor.selectOptions(role, "finance_staff")
  await actor.click(table.getByRole("button", { name: "查看 chen 的角色权限" }))
  expect(screen.getByRole("dialog", { name: "角色权限说明" })).toHaveTextContent("管理经营历程和采购单")
  await actor.keyboard("{Escape}")
  await actor.click(table.getByRole("button", { name: "保存账号 chen" }))
  await waitFor(() => expect(mocks.updateUser).toHaveBeenCalledWith(1, expect.objectContaining({
    department_code: "finance", role_code: "finance_staff",
  })))
})

test("retains unsaved changes after a save fails", async () => {
  const actor = userEvent.setup()
  mocks.updateUser.mockRejectedValueOnce(new Error("保存失败，请重试"))
  const table = await openTable()
  await actor.type(table.getByRole("textbox", { name: "chen的姓名" }), "改")
  await actor.click(table.getByRole("button", { name: "保存账号 chen" }))
  await screen.findByText("保存失败，请重试")
  expect(table.getByRole("textbox", { name: "chen的姓名" })).toHaveValue("陈杰改")
  expect(table.getByRole("button", { name: "保存账号 chen" })).toBeEnabled()
  expect(screen.getByRole("status")).toHaveTextContent("1 个账号待保存")
})

test("the mobile card shares edits, undo and password submission with the table", async () => {
  const actor = userEvent.setup()
  await openTable()
  const cards = within(screen.getByRole("group", { name: "账号卡片" }))
  const name = cards.getByRole("textbox", { name: "chen的姓名" })
  await actor.type(name, "改")
  await actor.click(cards.getByRole("button", { name: "撤销 chen 的修改" }))
  expect(name).toHaveValue("陈杰")
  await actor.type(cards.getByLabelText("chen的新密码"), "Updated-Password-123")
  await actor.click(cards.getByRole("button", { name: "保存账号 chen" }))
  await waitFor(() => expect(mocks.updateUser).toHaveBeenCalledWith(1, expect.objectContaining({
    password: "Updated-Password-123",
  })))
})
