import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { SidebarNav } from "@/components/sidebar-nav"

const { mockAuth } = vi.hoisted(() => ({
  mockAuth: {
    user: { role_code: "super_admin", department_code: "开发部" },
    hasPermission: vi.fn<(permission: string) => boolean>(),
    logout: vi.fn(),
  },
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/size-groups",
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => mockAuth,
}))

vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => null,
}))

describe("SidebarNav management groups", () => {
  beforeEach(() => {
    mockAuth.user = { role_code: "super_admin", department_code: "开发部" }
    mockAuth.hasPermission.mockReturnValue(true)
  })

  afterEach(cleanup)

  it("places product settings in other management and keeps system entries separate", () => {
    render(<SidebarNav />)

    const otherGroup = screen.getByRole("heading", { name: "其他管理" }).parentElement!
    const systemGroup = screen.getByRole("heading", { name: "系统管理" }).parentElement!

    expect(
      within(otherGroup).getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")])
    ).toEqual([
      ["尺码组管理", "/size-groups"],
      ["颜色管理", "/color-barcodes"],
      ["辅助属性管理", "/auxiliary-attributes"],
    ])
    expect(
      within(systemGroup).getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")])
    ).toEqual([
      ["用户管理", "/admin"],
      ["定时任务", "/scheduled-tasks"],
    ])
  })

  it("keeps product department access without showing an empty system group", () => {
    mockAuth.user = { role_code: "staff", department_code: "商品部" }
    mockAuth.hasPermission.mockImplementation((permission) => permission === "product.view")

    render(<SidebarNav />)

    const otherGroup = screen.getByRole("heading", { name: "其他管理" }).parentElement!
    expect(within(otherGroup).getAllByRole("link")).toHaveLength(3)
    expect(screen.queryByRole("heading", { name: "系统管理" })).not.toBeInTheDocument()
  })

  it("hides other management when the department cannot access its entries", () => {
    mockAuth.user = { role_code: "staff", department_code: "运营部" }
    mockAuth.hasPermission.mockImplementation((permission) => permission === "product.view")

    render(<SidebarNav />)

    expect(screen.queryByRole("heading", { name: "其他管理" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "尺码组管理" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "颜色管理" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "辅助属性管理" })).not.toBeInTheDocument()
  })
})
