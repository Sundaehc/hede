import { useState } from "react"
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { InventoryProductCodeFilter } from "@/components/inventory-admin/product-code-filter"
import type { InventoryDetailCandidate } from "@/lib/api"

const { listCandidates } = vi.hoisted(() => ({ listCandidates: vi.fn() }))

vi.mock("@/lib/api", () => ({ listInventoryDetailCandidates: listCandidates }))

const candidate: InventoryDetailCandidate = {
  product_code: "QT653891S73",
  sku: "QT653891S73",
  original_sku: "QT653891",
  product_name: "休闲鞋",
  color_name: "黑色",
  factory_code: "FACTORY-001",
  brand: "cbanner_mens",
}

function FilterHarness({ value = "", onSubmit = vi.fn() }: { value?: string; onSubmit?: () => void }) {
  const [code, setCode] = useState(value)
  return <InventoryProductCodeFilter value={code} onChange={setCode} onSubmit={onSubmit} />
}

async function advanceDebounce(milliseconds = 220) {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds) })
}

beforeEach(() => {
  vi.useFakeTimers()
  listCandidates.mockReset()
  listCandidates.mockResolvedValue({ items: [candidate] })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("InventoryProductCodeFilter", () => {
  it("requests candidates only after two characters and debounces typing", async () => {
    render(<FilterHarness />)
    const input = screen.getByRole("combobox")
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: "Q" } })
    await advanceDebounce()
    expect(listCandidates).not.toHaveBeenCalled()
    expect(screen.getByText("输入至少 2 个字符匹配商品编码")).toBeInTheDocument()

    fireEvent.change(input, { target: { value: "QT" } })
    await advanceDebounce(100)
    fireEvent.change(input, { target: { value: "QT65" } })
    await advanceDebounce(219)
    expect(listCandidates).not.toHaveBeenCalled()
    expect(screen.getByText("匹配中...")).toBeInTheDocument()
    await advanceDebounce(1)
    expect(listCandidates).toHaveBeenCalledExactlyOnceWith({ query: "QT65", limit: 20 })
    expect(screen.getByRole("button", { name: "QT653891S73" })).toBeInTheDocument()
    expect(screen.queryByText(/休闲鞋|黑色/)).not.toBeInTheDocument()
  })

  it("selects a candidate without submitting and deduplicates product codes", async () => {
    listCandidates.mockResolvedValue({ items: [candidate, { ...candidate, brand: "cbanner_womens" }] })
    const onSubmit = vi.fn()
    render(<FilterHarness onSubmit={onSubmit} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "QT65" } })
    await advanceDebounce()

    const options = screen.getAllByRole("button", { name: "QT653891S73" })
    expect(options).toHaveLength(1)
    fireEvent.click(options[0])
    expect(input).toHaveValue("QT653891S73")
    expect(input).toHaveAttribute("aria-expanded", "false")
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("preserves manual fuzzy search on Enter even when one candidate matches", async () => {
    const onSubmit = vi.fn()
    render(<FilterHarness onSubmit={onSubmit} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "QT65" } })
    await advanceDebounce()
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(input).toHaveValue("QT65")
    expect(input).toHaveAttribute("aria-expanded", "false")
  })

  it("keeps candidates matched through original or factory codes visible", async () => {
    render(<FilterHarness />)
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "FACTORY" } })
    await advanceDebounce()
    expect(screen.getByRole("button", { name: "QT653891S73" })).toBeInTheDocument()
  })

  it("hides stale candidates immediately and ignores late responses", async () => {
    let resolveOld: (response: { items: InventoryDetailCandidate[] }) => void = () => {}
    listCandidates.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
    const newCandidate = { ...candidate, product_code: "RF661500D24", sku: "RF661500D24", original_sku: "RF661500" }
    listCandidates.mockResolvedValue({ items: [newCandidate] })
    render(<FilterHarness />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "QT65" } })
    await advanceDebounce()
    fireEvent.change(input, { target: { value: "RF66" } })
    await advanceDebounce()
    expect(screen.getByRole("button", { name: "RF661500D24" })).toBeInTheDocument()

    await act(async () => { resolveOld({ items: [candidate] }) })
    expect(screen.getByRole("button", { name: "RF661500D24" })).toBeInTheDocument()
    fireEvent.change(input, { target: { value: "QT65" } })
    expect(screen.queryByRole("button", { name: "RF661500D24" })).not.toBeInTheDocument()
    expect(screen.getByText("匹配中...")).toBeInTheDocument()
  })

  it.each([
    ["empty", "没有匹配商品，可直接输入编码搜索"],
    ["failure", "候选加载失败，可直接输入编码搜索"],
  ])("allows manual search after an %s response", async (response, message) => {
    if (response === "failure") listCandidates.mockRejectedValue(new Error("offline"))
    else listCandidates.mockResolvedValue({ items: [] })
    const onSubmit = vi.fn()
    render(<FilterHarness onSubmit={onSubmit} />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "QT65" } })
    await advanceDebounce()
    expect(screen.getByText(message)).toBeInTheDocument()
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(input).toHaveValue("QT65")
  })

  it("clears the code and cancels pending requests", async () => {
    render(<FilterHarness />)
    const input = screen.getByRole("combobox")
    fireEvent.change(input, { target: { value: "QT65" } })
    fireEvent.click(screen.getByRole("button", { name: "清空" }))
    await advanceDebounce()
    expect(input).toHaveValue("")
    expect(listCandidates).not.toHaveBeenCalled()
    fireEvent.focus(input)
    expect(screen.getByText("输入至少 2 个字符匹配商品编码")).toBeInTheDocument()
  })
})
