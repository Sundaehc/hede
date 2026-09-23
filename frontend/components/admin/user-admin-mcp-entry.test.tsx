import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { UserAdminPage } from "@/components/admin/user-admin-page"

const mocks = vi.hoisted(() => ({
  auth: {
    user: { role_code: "super_admin" },
    hasPermission: vi.fn(),
  },
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => mocks.auth,
}))
vi.mock("@/components/operation-log-dialog", () => ({
  OperationLogDialog: () => null,
}))
vi.mock("@/lib/api", () => ({
  createAdminUser: vi.fn(),
  updateAdminUser: vi.fn(),
  getAuthOptions: async () => ({ departments: [], roles: [] }),
  listAdminUsers: async () => ({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
    stats: { active: 0, disabled: 0, department_count: 0 },
  }),
}))

beforeEach(() => {
  mocks.auth.user.role_code = "super_admin"
  mocks.auth.hasPermission.mockReturnValue(true)
})
afterEach(cleanup)

describe("User administration MCP entry", () => {
  it("links super administrators to the token management page", async () => {
    render(<UserAdminPage />)
    expect(
      await screen.findByRole("link", { name: "MCP Token 管理" })
    ).toHaveAttribute("href", "/admin/mcp-tokens")
    await screen.findByRole("heading", { name: "用户管理", level: 1 })
  })

  it("does not expose the entry to other roles with system.admin", async () => {
    mocks.auth.user.role_code = "staff"
    render(<UserAdminPage />)
    await screen.findByRole("heading", { name: "用户管理", level: 1 })
    expect(
      screen.queryByRole("link", { name: "MCP Token 管理" })
    ).not.toBeInTheDocument()
  })
})
