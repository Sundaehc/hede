import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { UserAdminPage } from "@/components/admin/user-admin-page"

const mocks = vi.hoisted(() => ({
  listAdminUsers: vi.fn(),
  hasPermission: () => true,
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role_code: "super_admin" }, hasPermission: mocks.hasPermission }),
}))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", () => ({
  createAdminUser: vi.fn(),
  updateAdminUser: vi.fn(),
  getAuthOptions: async () => ({ departments: [], roles: [] }),
  listAdminUsers: mocks.listAdminUsers,
}))

beforeEach(() => {
  mocks.listAdminUsers.mockReset()
  mocks.listAdminUsers.mockImplementation(async ({ page, pageSize, nameQuery }) => ({
    items: [],
    total: nameQuery ? 0 : 41,
    page,
    page_size: pageSize,
    stats: { active: nameQuery ? 0 : 41, disabled: 0, department_count: nameQuery ? 0 : 1 },
  }))
})
afterEach(cleanup)

describe("User name filtering", () => {
  it("submits a partial name and resets pagination to the first page", async () => {
    const actor = userEvent.setup()
    render(<UserAdminPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
    await actor.click(screen.getByText("下一页"))
    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 2, pageSize: 20, nameQuery: undefined }))

    await actor.type(screen.getByRole("textbox", { name: "姓名筛选" }), " 张 ")
    expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 2, pageSize: 20, nameQuery: undefined })
    await actor.click(screen.getByRole("button", { name: "查询" }))

    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, nameQuery: "张" }))
    expect(screen.getAllByText("未找到匹配姓名的用户")).toHaveLength(2)
  })

  it("supports Enter to search and clearing the name filter", async () => {
    const actor = userEvent.setup()
    render(<UserAdminPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
    await actor.type(screen.getByRole("textbox", { name: "姓名筛选" }), "李{Enter}")
    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, nameQuery: "李" }))
    await waitFor(() => expect(screen.getByRole("button", { name: "清空" })).toBeEnabled())

    await actor.click(screen.getByRole("button", { name: "清空" }))

    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, nameQuery: undefined }))
    expect(screen.getByRole("textbox", { name: "姓名筛选" })).toHaveValue("")
  })

  it("preserves the submitted name filter when changing pages and page size", async () => {
    mocks.listAdminUsers.mockImplementation(async ({ page, pageSize }) => ({
      items: [], total: 41, page, page_size: pageSize,
      stats: { active: 41, disabled: 0, department_count: 1 },
    }))
    const actor = userEvent.setup()
    render(<UserAdminPage />)
    await waitFor(() => expect(screen.getByRole("button", { name: "查询" })).toBeEnabled())
    await actor.type(screen.getByRole("textbox", { name: "姓名筛选" }), "张{Enter}")
    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, nameQuery: "张" }))

    await actor.click(screen.getByText("下一页"))
    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 2, pageSize: 20, nameQuery: "张" }))
    await actor.selectOptions(screen.getByRole("combobox", { name: "每页显示条数" }), "50")
    await waitFor(() => expect(mocks.listAdminUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 50, nameQuery: "张" }))
  })
})
