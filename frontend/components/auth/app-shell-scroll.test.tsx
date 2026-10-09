import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { AppShell } from "@/components/auth/app-shell"

const { navigation, auth } = vi.hoisted(() => ({
  navigation: { pathname: "/inventory", replace: vi.fn() },
  auth: { loading: false, user: { id: 1 } as { id: number } | null },
}))

vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname, useRouter: () => ({ replace: navigation.replace }) }))
vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => auth }))
vi.mock("@/components/sidebar-nav", () => ({ SidebarNav: () => <nav>侧边栏</nav> }))
vi.mock("@/lib/session-query-state", () => ({ SessionQueryProvider: ({ children }: { children: React.ReactNode }) => children }))
vi.mock("@/lib/session-scroll-restoration", () => ({
  SessionScrollRestoration: ({ pathname, userId, children }: { pathname: string; userId: number; children: React.ReactNode }) => <div data-testid="scroll-scope" data-pathname={pathname} data-user-id={userId}>{children}</div>,
}))

beforeEach(() => {
  navigation.pathname = "/inventory"
  navigation.replace.mockReset()
  auth.loading = false
  auth.user = { id: 1 }
})

afterEach(cleanup)

test("applies scroll restoration to every authenticated page using its route and user", () => {
  const view = render(<AppShell><p>单据列表</p></AppShell>)
  expect(screen.getByTestId("scroll-scope")).toHaveAttribute("data-pathname", "/inventory")
  expect(screen.getByTestId("scroll-scope")).toHaveAttribute("data-user-id", "1")
  navigation.pathname = "/products"
  view.rerender(<AppShell><p>商品列表</p></AppShell>)
  expect(screen.getByTestId("scroll-scope")).toHaveAttribute("data-pathname", "/products")
  expect(screen.getByText("商品列表")).toBeInTheDocument()
  auth.user = { id: 2 }
  view.rerender(<AppShell><p>新用户列表</p></AppShell>)
  expect(screen.getByTestId("scroll-scope")).toHaveAttribute("data-user-id", "2")
})

test("does not apply cached page positions to the login screen", () => {
  navigation.pathname = "/login"
  auth.user = null
  render(<AppShell><p>登录</p></AppShell>)
  expect(screen.queryByTestId("scroll-scope")).not.toBeInTheDocument()
  expect(screen.getByText("登录")).toBeInTheDocument()
})
