import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { StrictMode } from "react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { PageTabs } from "@/components/auth/page-tabs"
import { SessionQueryProvider } from "@/lib/session-query-state"
import { usePurchaseDetailTabs } from "@/lib/purchase-detail-tabs"
import type { AuthUser } from "@/lib/types"

const { navigation, auth, api } = vi.hoisted(() => ({
  navigation: { pathname: "/products", push: vi.fn() },
  auth: { user: { id: 1, role_code: "super_admin", department_code: "开发部" } as AuthUser, hasPermission: vi.fn() },
  api: { getPinnedPageTabs: vi.fn(), setPageTabPinned: vi.fn() },
}))

vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname, useRouter: () => ({ push: navigation.push }) }))
vi.mock("@/components/auth/auth-provider", () => ({ useAuth: () => auth }))
vi.mock("@/lib/api", () => api)

function fixture() {
  return <SessionQueryProvider key={auth.user.id} userId={auth.user.id}><PageTabs key={auth.user.id} /></SessionQueryProvider>
}

function visitPage(view: ReturnType<typeof render>, pathname: string) {
  navigation.pathname = pathname
  view.rerender(fixture())
}

async function waitForPinsLoaded() {
  await waitFor(() => expect(api.getPinnedPageTabs).toHaveBeenCalled())
  await act(async () => {})
}

beforeEach(() => {
  navigation.pathname = "/products"
  navigation.push.mockReset()
  auth.user = { id: 1, role_code: "super_admin", department_code: "开发部" } as AuthUser
  auth.hasPermission.mockReturnValue(true)
  api.getPinnedPageTabs.mockReset().mockResolvedValue({ pinned_paths: [] })
  api.setPageTabPinned.mockReset()
})

afterEach(cleanup)

test("uses compact icon tabs with a distinct active state and keeps the existing overlay layer", async () => {
  const view = render(fixture())
  await waitForPinsLoaded()
  visitPage(view, "/inventory")
  visitPage(view, "/products")
  const current = screen.getByRole("link", { name: "商品信息档案" })
  const inactive = screen.getByRole("link", { name: "经营历程" })
  expect(current.parentElement).toHaveClass("h-8", "rounded-lg", "bg-sky-50", "dark:bg-sky-400/10")
  expect(inactive.parentElement).toHaveClass("border-transparent")
  expect(current).toHaveAttribute("title", "商品信息档案")
  expect(current.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
  expect(current.querySelector("span")).toHaveClass("truncate")
  expect(screen.getByRole("navigation", { name: "页面标签" }).closest("header")).toHaveClass("z-[70]", "h-[var(--page-tabs-height,2.75rem)]")
})

test("keeps subdued tab actions available by keyboard", async () => {
  const user = userEvent.setup()
  const view = render(fixture())
  await waitForPinsLoaded()
  visitPage(view, "/inventory")
  visitPage(view, "/products")
  await user.tab()
  expect(screen.getByRole("link", { name: "经营历程" })).toHaveFocus()
  await user.tab()
  const pin = screen.getByRole("button", { name: "固定经营历程" })
  expect(pin).toHaveFocus()
  expect(pin).toHaveClass("group-focus-within:opacity-100")
  await user.tab()
  expect(screen.getByRole("button", { name: "关闭经营历程" })).toHaveFocus()
})

test("starts with no tabs and automatically adds the destination when switching pages", async () => {
  const view = render(fixture())
  expect(within(screen.getByRole("navigation", { name: "页面标签" })).queryAllByRole("link")).toHaveLength(0)
  await waitForPinsLoaded()
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  expect(screen.getAllByRole("link")).toHaveLength(1)
  expect(screen.getByRole("link", { name: "经营历程" })).toHaveAttribute("aria-current", "page")
  expect(screen.queryByRole("link", { name: "商品信息档案" })).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "添加当前页标签" })).not.toBeInTheDocument()
  expect(api.setPageTabPinned).not.toHaveBeenCalled()
})

test("ignores previously cached automatically opened tabs", async () => {
  window.sessionStorage.setItem("hede:session-query:v1:1:workspace:open-tabs", JSON.stringify(["/products", "/inventory"]))
  render(fixture())
  await waitForPinsLoaded()
  expect(screen.queryAllByRole("link")).toHaveLength(0)
})

test("automatically adds visited pages and avoids duplicate tabs", async () => {
  const view = render(fixture())
  await waitForPinsLoaded()
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  expect(screen.getByRole("link", { name: "经营历程" })).toHaveAttribute("aria-current", "page")
  navigation.pathname = "/products"
  view.rerender(fixture())
  expect(screen.getByRole("link", { name: "商品信息档案" })).toHaveAttribute("aria-current", "page")
  expect(screen.getByRole("link", { name: "经营历程" })).not.toHaveAttribute("aria-current")
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  expect(screen.getAllByRole("link", { name: "商品信息档案" })).toHaveLength(1)
  expect(screen.getAllByRole("link", { name: "经营历程" })).toHaveLength(1)
  expect(screen.getAllByRole("link")).toHaveLength(2)
})

test("never shows a manual add-current-page control before or after navigation", async () => {
  const view = render(fixture())
  await waitForPinsLoaded()
  expect(screen.queryByRole("button", { name: "添加当前页标签" })).not.toBeInTheDocument()
  expect(screen.queryByText("添加当前页")).not.toBeInTheDocument()
  visitPage(view, "/inventory")
  expect(screen.getByRole("link", { name: "经营历程" })).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "添加当前页标签" })).not.toBeInTheDocument()
  expect(screen.queryByText("添加当前页")).not.toBeInTheDocument()
})

test("does not add the initial route during Strict Mode effect replay", async () => {
  const view = render(<StrictMode>{fixture()}</StrictMode>)
  await waitForPinsLoaded()
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  navigation.pathname = "/inventory"
  view.rerender(<StrictMode>{fixture()}</StrictMode>)
  expect(screen.getAllByRole("link", { name: "经营历程" })).toHaveLength(1)
})

test("pins an automatically added tab and restores only fixed tabs in a new browser session", async () => {
  api.setPageTabPinned.mockResolvedValue({ pinned_paths: ["/products"] })
  navigation.pathname = "/inventory"
  const view = render(fixture())
  visitPage(view, "/products")
  await waitFor(() => expect(screen.getByRole("button", { name: "固定商品信息档案" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "固定商品信息档案" }))
  await waitFor(() => expect(screen.getByRole("button", { name: "取消固定商品信息档案" })).toHaveAttribute("aria-pressed", "true"))
  expect(api.setPageTabPinned).toHaveBeenCalledWith("/products", true)
  expect(screen.queryByRole("button", { name: "关闭商品信息档案" })).not.toBeInTheDocument()
  view.unmount()
  window.sessionStorage.clear()
  navigation.pathname = "/inventory"
  api.getPinnedPageTabs.mockResolvedValue({ pinned_paths: ["/products"] })
  render(fixture())
  await screen.findByRole("button", { name: "取消固定商品信息档案" })
  expect(screen.queryByRole("link", { name: "经营历程" })).not.toBeInTheDocument()
})

test("keeps visited tabs when remounting within the same session", async () => {
  navigation.pathname = "/inventory"
  const view = render(fixture())
  visitPage(view, "/products")
  await waitForPinsLoaded()
  view.unmount()
  navigation.pathname = "/inventory"
  render(fixture())
  await waitForPinsLoaded()
  expect(screen.getByRole("link", { name: "商品信息档案" })).toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "经营历程" })).not.toBeInTheDocument()
})

test("keeps an unpinned tab open and allows closing it", async () => {
  api.getPinnedPageTabs.mockResolvedValue({ pinned_paths: ["/inventory"] })
  api.setPageTabPinned.mockResolvedValue({ pinned_paths: [] })
  render(fixture())
  await screen.findByRole("button", { name: "取消固定经营历程" })
  fireEvent.click(screen.getByRole("button", { name: "取消固定经营历程" }))
  await screen.findByRole("button", { name: "关闭经营历程" })
  expect(api.setPageTabPinned).toHaveBeenCalledWith("/inventory", false)
  fireEvent.click(screen.getByRole("button", { name: "关闭经营历程" }))
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  expect(navigation.push).not.toHaveBeenCalled()
})

test("closing the active tab switches to its neighbour and does not reopen it", async () => {
  const view = render(fixture())
  await waitForPinsLoaded()
  visitPage(view, "/inventory")
  visitPage(view, "/products")
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  fireEvent.click(screen.getByRole("button", { name: "关闭经营历程" }))
  expect(navigation.push).toHaveBeenCalledWith("/products", { scroll: false })
  navigation.pathname = "/products"
  view.rerender(fixture())
  expect(screen.queryByRole("link", { name: "经营历程" })).not.toBeInTheDocument()
})

test("reopens a closed page only when visiting it again", async () => {
  const view = render(fixture())
  await waitForPinsLoaded()
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  fireEvent.click(screen.getByRole("button", { name: "关闭经营历程" }))
  view.rerender(fixture())
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  expect(navigation.push).not.toHaveBeenCalled()
  navigation.pathname = "/products"
  view.rerender(fixture())
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  expect(screen.getAllByRole("link", { name: "经营历程" })).toHaveLength(1)
})

test.each(["/products", "/inventory"])("allows closing the last tab without leaving %s or adding a default tab", async (pathname) => {
  navigation.pathname = pathname === "/products" ? "/inventory" : "/products"
  const view = render(fixture())
  visitPage(view, pathname)
  await waitForPinsLoaded()
  const label = pathname === "/products" ? "商品信息档案" : "经营历程"
  expect(screen.getByRole("button", { name: `关闭${label}` })).toBeEnabled()
  fireEvent.click(screen.getByRole("button", { name: `关闭${label}` }))
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  expect(navigation.push).not.toHaveBeenCalled()
  view.rerender(fixture())
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  view.unmount()
  render(fixture())
  await waitForPinsLoaded()
  expect(screen.queryAllByRole("link")).toHaveLength(0)
})

test("isolates fixed and visited tabs when changing accounts and ignores stale responses", async () => {
  let resolveFirst!: (value: { pinned_paths: string[] }) => void
  api.getPinnedPageTabs.mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
  navigation.pathname = "/inventory"
  const view = render(fixture())
  visitPage(view, "/products")
  auth.user = { ...auth.user, id: 2 }
  navigation.pathname = "/inventory"
  api.getPinnedPageTabs.mockResolvedValue({ pinned_paths: ["/suppliers"] })
  view.rerender(fixture())
  await screen.findByRole("button", { name: "取消固定供应商管理" })
  await act(async () => resolveFirst({ pinned_paths: ["/products"] }))
  expect(screen.queryByRole("link", { name: "商品信息档案" })).not.toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "经营历程" })).not.toBeInTheDocument()
  expect(screen.getAllByRole("link")).toHaveLength(1)
})

test("hides pinned and session tabs outside the current account permissions", async () => {
  auth.user = { ...auth.user, role_code: "staff", department_code: "商品部" }
  auth.hasPermission.mockImplementation((permission) => permission === "product.view")
  window.sessionStorage.setItem("hede:session-query:v1:1:workspace:manual-tabs", JSON.stringify(["/admin", "/inventory", "/products"]))
  api.getPinnedPageTabs.mockResolvedValue({ pinned_paths: ["/admin", "/inventory", "/suppliers", "/size-groups", "/does-not-exist"] })
  render(fixture())
  await screen.findByRole("button", { name: "取消固定尺码组管理" })
  expect(screen.queryByRole("link", { name: "用户管理" })).not.toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "经营历程" })).not.toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "供应商管理" })).not.toBeInTheDocument()
  expect(screen.getAllByRole("link")).toHaveLength(2)
})

test("failed pin saves show an error without marking the page as fixed", async () => {
  api.setPageTabPinned.mockRejectedValue(new Error("offline"))
  navigation.pathname = "/inventory"
  const view = render(fixture())
  visitPage(view, "/products")
  await waitFor(() => expect(screen.getByRole("button", { name: "固定商品信息档案" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "固定商品信息档案" }))
  await screen.findByRole("alert")
  expect(screen.getByRole("button", { name: "固定商品信息档案" })).toHaveAttribute("aria-pressed", "false")
  expect(screen.getByRole("button", { name: "关闭商品信息档案" })).toBeInTheDocument()
})

test("failed loads keep initial tabs empty and still allow automatic navigation without pinning", async () => {
  api.getPinnedPageTabs.mockRejectedValue(new Error("offline"))
  navigation.pathname = "/inventory"
  const view = render(fixture())
  await screen.findByRole("alert")
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  visitPage(view, "/products")
  expect(screen.getByRole("link", { name: "商品信息档案" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "固定商品信息档案" })).toBeDisabled()
})

test("disables concurrent pin changes until the current save finishes", async () => {
  let resolveSave!: (value: { pinned_paths: string[] }) => void
  api.getPinnedPageTabs.mockResolvedValue({ pinned_paths: ["/inventory"] })
  api.setPageTabPinned.mockReturnValue(new Promise((resolve) => { resolveSave = resolve }))
  navigation.pathname = "/inventory"
  const view = render(fixture())
  visitPage(view, "/products")
  await screen.findByRole("button", { name: "取消固定经营历程" })
  fireEvent.click(screen.getByRole("button", { name: "固定商品信息档案" }))
  expect(screen.getByRole("button", { name: "取消固定经营历程" })).toBeDisabled()
  expect(screen.getByRole("button", { name: "固定商品信息档案" })).toBeDisabled()
  await act(async () => resolveSave({ pinned_paths: ["/inventory", "/products"] }))
  expect(screen.getByRole("button", { name: "取消固定经营历程" })).toBeEnabled()
  expect(screen.getByRole("button", { name: "取消固定商品信息档案" })).toBeEnabled()
})

test("automatically adds the MCP account management subpage when visited", async () => {
  const view = render(fixture())
  expect(screen.queryByRole("link", { name: "MCP 令牌管理" })).not.toBeInTheDocument()
  visitPage(view, "/admin/mcp-tokens")
  await waitFor(() => expect(screen.getByRole("button", { name: "固定MCP 令牌管理" })).toBeEnabled())
  expect(screen.getByRole("link", { name: "MCP 令牌管理" })).toHaveAttribute("aria-current", "page")
})

test("does not add inaccessible or unknown pages", async () => {
  navigation.pathname = "/unknown"
  render(fixture())
  await waitForPinsLoaded()
  expect(screen.queryByRole("button", { name: "添加当前页标签" })).not.toBeInTheDocument()
  expect(screen.queryAllByRole("link")).toHaveLength(0)
})

test("automatic navigation skips inaccessible pages without blocking later valid visits", async () => {
  auth.user = { ...auth.user, role_code: "staff", department_code: "商品部" }
  auth.hasPermission.mockImplementation((permission) => permission === "product.view")
  const view = render(fixture())
  await waitForPinsLoaded()
  navigation.pathname = "/inventory"
  view.rerender(fixture())
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  navigation.pathname = "/unknown"
  view.rerender(fixture())
  expect(screen.queryAllByRole("link")).toHaveLength(0)
  navigation.pathname = "/products"
  view.rerender(fixture())
  expect(screen.getByRole("link", { name: "商品信息档案" })).toHaveAttribute("aria-current", "page")
})

function DetailOpeners() {
  const { openDetail, updateDetail } = usePurchaseDetailTabs()
  return <><button onClick={() => openDetail(42, "PO-42", "秋冬补货采购")}>打开明细甲</button><button onClick={() => openDetail(43, "PO-43")}>打开明细乙</button><button onClick={() => updateDetail(42, "PO-42", "秋冬补货采购（已更新）")}>更新明细甲摘要</button></>
}

function detailFixture() {
  return <SessionQueryProvider key={auth.user.id} userId={auth.user.id}><PageTabs key={auth.user.id} /><DetailOpeners /></SessionQueryProvider>
}

test("opens one independent tab per purchase document and activates the document rather than its list", async () => {
  navigation.pathname = "/purchase-orders"
  const view = render(detailFixture())
  await waitForPinsLoaded()
  fireEvent.click(screen.getByText("打开明细甲"))
  fireEvent.click(screen.getByText("打开明细甲"))
  fireEvent.click(screen.getByText("打开明细乙"))
  expect(screen.getAllByRole("link", { name: "秋冬补货采购" })).toHaveLength(1)
  expect(screen.getByRole("link", { name: "秋冬补货采购" })).toHaveAttribute("href", "/purchase-orders/42")
  expect(screen.getByRole("link", { name: "秋冬补货采购" })).toHaveAttribute("title", "秋冬补货采购")
  expect(screen.queryByRole("button", { name: "固定秋冬补货采购" })).not.toBeInTheDocument()
  expect(screen.getByRole("link", { name: "PO-43" })).toHaveAttribute("href", "/purchase-orders/43")
  navigation.pathname = "/purchase-orders/42"
  view.rerender(detailFixture())
  expect(screen.getByRole("link", { name: "秋冬补货采购" })).toHaveAttribute("aria-current", "page")
  fireEvent.click(screen.getByText("更新明细甲摘要"))
  expect(screen.queryByRole("link", { name: "秋冬补货采购" })).not.toBeInTheDocument()
  expect(screen.getByRole("link", { name: "秋冬补货采购（已更新）" })).toHaveAttribute("aria-current", "page")
  expect(screen.getByRole("link", { name: "采购单管理" })).not.toHaveAttribute("aria-current")
  expect(api.setPageTabPinned).not.toHaveBeenCalled()
})

test("closing background and current document tabs removes their saved entries and returns to the list", async () => {
  navigation.pathname = "/purchase-orders"
  const view = render(detailFixture())
  await waitForPinsLoaded()
  fireEvent.click(screen.getByText("打开明细甲"))
  fireEvent.click(screen.getByText("打开明细乙"))
  navigation.pathname = "/purchase-orders/42"
  view.rerender(detailFixture())
  fireEvent.click(screen.getByRole("button", { name: "关闭PO-43" }))
  expect(navigation.push).not.toHaveBeenCalled()
  expect(screen.queryByRole("link", { name: "PO-43" })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "关闭秋冬补货采购" }))
  expect(navigation.push).toHaveBeenLastCalledWith("/purchase-orders", { scroll: false })
  navigation.pathname = "/purchase-orders"
  view.rerender(detailFixture())
  expect(screen.queryByRole("link", { name: "秋冬补货采购" })).not.toBeInTheDocument()
  view.unmount()
  render(detailFixture())
  await waitForPinsLoaded()
  expect(screen.queryByRole("link", { name: "秋冬补货采购" })).not.toBeInTheDocument()
})

test("restores document tabs in the same session and isolates their summaries between accounts", async () => {
  navigation.pathname = "/purchase-orders"
  const view = render(detailFixture())
  await waitForPinsLoaded()
  fireEvent.click(screen.getByText("打开明细甲"))
  view.unmount()
  const restored = render(detailFixture())
  expect(screen.getByRole("link", { name: "秋冬补货采购" })).toBeInTheDocument()
  auth.user = { ...auth.user, id: 2 }
  restored.rerender(detailFixture())
  await waitForPinsLoaded()
  expect(screen.queryByRole("link", { name: "秋冬补货采购" })).not.toBeInTheDocument()
})

test("shows a direct document route before its summary loads and hides document tabs without purchase access", async () => {
  navigation.pathname = "/purchase-orders/42"
  const view = render(detailFixture())
  await waitForPinsLoaded()
  expect(screen.getByRole("link", { name: "42" })).toHaveAttribute("aria-current", "page")
  fireEvent.click(screen.getByText("打开明细甲"))
  expect(screen.getByRole("link", { name: "秋冬补货采购" })).toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "42" })).not.toBeInTheDocument()
  auth.user = { ...auth.user, role_code: "staff", department_code: "商品部" }
  auth.hasPermission.mockImplementation((permission) => permission === "product.view")
  view.rerender(detailFixture())
  expect(screen.queryByRole("link", { name: "秋冬补货采购" })).not.toBeInTheDocument()
})

test("scrolls automatically added overflowing tabs horizontally without changing the page scroll", async () => {
  const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { left: 100, right: this.tagName === "NAV" ? 300 : 500 } as DOMRect
  })
  const pageScroll = vi.spyOn(window, "scrollTo").mockImplementation(() => {})
  try {
    navigation.pathname = "/inventory"
    const view = render(fixture())
    visitPage(view, "/products")
    await waitFor(() => expect(screen.getByRole("button", { name: "固定商品信息档案" })).toBeEnabled())
    expect(screen.getByRole("navigation", { name: "页面标签" }).scrollLeft).toBeGreaterThan(0)
    expect(pageScroll).not.toHaveBeenCalled()
  } finally {
    bounds.mockRestore()
    pageScroll.mockRestore()
  }
})
