import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import SuppliersPage from "@/app/suppliers/page"
import { ColorBarcodeManagementPage } from "@/components/color-barcodes/color-barcode-management-page"

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role_code: "super_admin" }, hasPermission: () => true }),
}))
vi.mock("@/components/operation-log-dialog", () => ({ OperationLogDialog: () => null }))
vi.mock("@/components/inventory-admin/counterparty-ledger-dialog", () => ({ CounterpartyLedgerDialog: () => null }))

const cases = [
  { kind: "color", Component: ColorBarcodeManagementPage, createLabel: "新增颜色", nameLabel: "颜色名称", codeLabel: "颜色代码", endpoint: "/api/color-barcodes", name: "米白色", conflict: "颜色代码“001”已在其他品牌中使用：自定义品牌（白色）。是否继续创建？" },
  { kind: "supplier", Component: SuppliersPage, createLabel: "新增供应商", nameLabel: "名称 *", codeLabel: "工厂代码", endpoint: "/api/suppliers", name: "新鞋厂", conflict: "工厂代码“001”已在其他品牌中使用：自定义品牌（原鞋厂）。是否继续创建？" },
] as const

beforeEach(() => window.sessionStorage.clear())
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe.each(cases)("$kind cross-brand code creation", (scenario) => {
  function mockServer(failure: 409 | 400 | null = 409) {
    const posts: { confirmed: boolean; payload: Record<string, string> }[] = []
    let created = false
    const item = scenario.kind === "color"
      ? { id: 7, brand: "cbanner_mens", brand_label: "千百度男鞋", color_barcode: "001", color_name: scenario.name, updated_at: null }
      : { id: 7, brand: "cbanner_mens", name: scenario.name, factory_code: "001" }
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost")
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
      if (init?.method === "POST") {
        expect(url.pathname).toBe(scenario.endpoint)
        const confirmed = url.searchParams.get("confirm_cross_brand_code") === "true"
        posts.push({ confirmed, payload: JSON.parse(String(init.body)) })
        if (failure === 400) return json({ detail: "同一品牌中该记录已存在" }, 400)
        if (failure === 409 && !confirmed) return json({ detail: scenario.conflict }, 409)
        created = true
        return json({ item, message: "新增成功", synced: { updated: 0 } })
      }
      if (url.pathname === "/api/color-barcodes/brands") {
        return json({ items: [{ brand: "cbanner_mens", brand_label: "千百度男鞋", total: created ? 1 : 0 }] })
      }
      if (url.pathname === "/api/supplier-brands") {
        return json({ items: [{ id: 1, code: "cbanner_mens", name: "千百度男鞋" }] })
      }
      if (url.pathname === scenario.endpoint) {
        return json({ items: created ? [item] : [], total: created ? 1 : 0, page: 1, page_size: 50 })
      }
      throw new Error(`Unexpected request: ${url.pathname}`)
    })
    return posts
  }

  async function fillForm() {
    const user = userEvent.setup()
    render(<scenario.Component />)
    await waitFor(() => expect(screen.getByRole("button", { name: scenario.createLabel })).toBeEnabled())
    await user.click(screen.getByRole("button", { name: scenario.createLabel }))
    const form = screen.getByRole("dialog", { name: scenario.createLabel })
    await user.type(within(form).getByLabelText(scenario.nameLabel), scenario.name)
    await user.type(within(form).getByLabelText(scenario.codeLabel), "001")
    await user.click(within(form).getByRole("button", { name: "保存" }))
    return user
  }

  it("cancels without creating and keeps the entered values", async () => {
    const posts = mockServer()
    const user = await fillForm()
    const warning = await screen.findByRole("alertdialog")
    expect(within(warning).getByText(scenario.conflict)).toBeVisible()
    expect(posts).toHaveLength(1)
    await user.click(within(warning).getByRole("button", { name: "取消创建" }))
    expect(posts).toHaveLength(1)
    const form = screen.getByRole("dialog", { name: scenario.createLabel })
    expect(within(form).getByLabelText(scenario.nameLabel)).toHaveValue(scenario.name)
    expect(within(form).getByLabelText(scenario.codeLabel)).toHaveValue("001")
  })

  it("creates only after confirmation, then refreshes the list", async () => {
    const posts = mockServer()
    const user = await fillForm()
    const warning = await screen.findByRole("alertdialog")
    await user.click(within(warning).getByRole("button", { name: "继续创建" }))
    await waitFor(() => expect(screen.queryByRole("dialog", { name: scenario.createLabel })).not.toBeInTheDocument())
    expect(posts).toHaveLength(2)
    expect(posts.map((post) => post.confirmed)).toEqual([false, true])
    expect(posts[1].payload).toEqual(posts[0].payload)
    if (scenario.kind === "color") {
      await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "确定" }))
    }
    expect(await screen.findByRole("cell", { name: scenario.name })).toBeInTheDocument()
  })

  it("creates directly when there is no cross-brand duplicate", async () => {
    const posts = mockServer(null)
    await fillForm()
    await waitFor(() => expect(screen.queryByRole("dialog", { name: scenario.createLabel })).not.toBeInTheDocument())
    expect(posts).toHaveLength(1)
    expect(posts[0].confirmed).toBe(false)
  })

  it("keeps existing validation failures instead of offering to bypass them", async () => {
    mockServer(400)
    const user = await fillForm()
    const warning = await screen.findByRole("alertdialog")
    expect(within(warning).getByText("保存失败")).toBeVisible()
    expect(within(warning).queryByRole("button", { name: "继续创建" })).not.toBeInTheDocument()
    await user.click(within(warning).getByRole("button", { name: "确定" }))
    expect(screen.getByRole("dialog", { name: scenario.createLabel })).toBeInTheDocument()
  })
})
