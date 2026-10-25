import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { OperationLogDialog } from "@/components/operation-log-dialog"
import type { OperationLogItem } from "@/lib/types"

const { mockListOperationLogs } = vi.hoisted(() => ({
  mockListOperationLogs: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  listOperationLogs: mockListOperationLogs,
}))

const logItem: OperationLogItem = {
  id: 101,
  module: "account_subject",
  action: "update",
  entity_type: "account_subject",
  entity_id: "20",
  entity_label: "鞋花费用",
  summary: "更新费用科目",
  changed_fields: null,
  before_data: null,
  after_data: null,
  user_id: 1,
  username: "admin",
  display_name: "管理员",
  department_name: null,
  created_at: "2026-10-14T08:00:00Z",
}

beforeEach(() => mockListOperationLogs.mockReset())
afterEach(cleanup)

test.each(["warehouse", "general_customer"] as const)(
  "displays reorder actions in Chinese for %s logs",
  async (module) => {
    mockListOperationLogs.mockResolvedValue({
      items: [{ ...logItem, module, action: "reorder" }],
      total: 1,
      page: 1,
      page_size: 20,
    })

    render(
      <OperationLogDialog
        module={module}
        open
        title="操作日志"
        onOpenChange={vi.fn()}
      />
    )

    const actionLabel = await screen.findByText("调整排序")
    const actionCell = within(actionLabel.closest("tr")!).getAllByRole("cell")[2]

    expect(actionCell).toHaveTextContent("调整排序")
    expect(actionLabel).toHaveAttribute("title", "调整排序")
    expect(screen.queryByText("reorder")).not.toBeInTheDocument()
    expect(screen.queryByTitle("reorder")).not.toBeInTheDocument()
  }
)

test.each(["permanent_delete", "batch_permanent_delete"])(
  "displays %s actions and tooltips in Chinese",
  async (action) => {
    mockListOperationLogs.mockResolvedValue({
      items: [{ ...logItem, module: "product", action }],
      total: 1,
      page: 1,
      page_size: 20,
    })

    render(
      <OperationLogDialog
        module="product"
        open
        title="商品操作日志"
        onOpenChange={vi.fn()}
      />
    )

    const actionLabel = await screen.findByText("彻底删除")
    const actionCell = within(actionLabel.closest("tr")!).getAllByRole("cell")[2]
    expect(actionCell).toHaveTextContent("彻底删除")
    expect(actionLabel).toHaveAttribute("title", "彻底删除")
    expect(screen.queryByText(action)).not.toBeInTheDocument()
    expect(screen.queryByTitle(action)).not.toBeInTheDocument()
  }
)

test.each([
  { entityLabel: "鞋花费用", expectedLabel: "鞋花费用" },
  { entityLabel: null, expectedLabel: "-" },
])(
  "keeps object label $expectedLabel without displaying its ID",
  async ({ entityLabel, expectedLabel }) => {
    mockListOperationLogs.mockResolvedValue({
      items: [{ ...logItem, entity_label: entityLabel }],
      total: 1,
      page: 1,
      page_size: 20,
    })

    render(
      <OperationLogDialog
        module="account_subject"
        open
        title="科目操作日志"
        onOpenChange={vi.fn()}
      />
    )

    const summary = await screen.findByText("更新费用科目")
    const row = summary.closest("tr")!
    const objectCell = within(row).getAllByRole("cell")[3]

    expect(objectCell.textContent).toBe(expectedLabel)
    expect(within(objectCell).queryByText("20")).not.toBeInTheDocument()
    expect(within(objectCell).queryByTitle("20")).not.toBeInTheDocument()
    expect(mockListOperationLogs).toHaveBeenCalledWith({
      module: "account_subject",
      page: 1,
      pageSize: 20,
      query: undefined,
    })
  }
)
