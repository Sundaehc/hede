import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"

import { ScheduledTaskPage } from "@/components/scheduled-tasks/scheduled-task-page"
import type { ScheduledTaskRunItem } from "@/lib/types"

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  listHistory: vi.fn(),
  listBusiness: vi.fn(),
}))

vi.mock("@/components/auth/auth-provider", () => ({
  useAuth: () => ({ user: { role_code: "super_admin" } }),
}))
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  listScheduledTaskRuns: mocks.listRuns,
  listScheduledTaskHistory: mocks.listHistory,
  listScheduledTaskBusinessStatuses: mocks.listBusiness,
}))

const longError = `IntegrityError: duplicate key\nDETAIL: goods code already exists\n${"product payload ".repeat(800)}`
const run: ScheduledTaskRunItem = {
  id: 1,
  task_name: "hede_import_gj_merged_product_info_daily",
  status: "failed",
  started_at: "2026-10-19T10:00:06+08:00",
  finished_at: "2026-10-19T10:00:22+08:00",
  duration_ms: 16719,
  exit_code: 1,
  host_name: "TEST-HOST",
  process_id: 1,
  command: "python -m scripts.import_gj_merged_product_info_daily",
  log_path: "logs/import_gj_merged_product_info.log",
  error_summary: longError,
  created_at: "2026-10-19T10:00:06+08:00",
}

beforeEach(() => {
  vi.resetAllMocks()
  window.sessionStorage.clear()
  mocks.listRuns.mockResolvedValue({
    items: [run],
    total: 1,
    page: 1,
    page_size: 50,
    summary: {
      total: 1,
      success: 0,
      failed: 1,
      running: 0,
      task_count: 1,
      latest_started_at: run.started_at,
    },
  })
  mocks.listHistory.mockResolvedValue({
    items: [run],
    task_name: run.task_name,
  })
  mocks.listBusiness.mockResolvedValue({
    items: [
      {
        id: 1,
        task_name: "import_gj_merged_product_info_daily",
        status: "failed",
        attempts: 1,
        source_path: null,
        message: longError,
        last_started_at: run.started_at,
        finished_at: run.finished_at,
      },
    ],
    total: 1,
    page: 1,
    page_size: 50,
    summary: { total: 1, success: 0, failed: 1, running: 0, skipped: 0 },
  })
})

afterEach(cleanup)

test("bounds errors in the main list and in expanded execution history", async () => {
  const user = userEvent.setup()
  const { container } = render(<ScheduledTaskPage />)
  await screen.findByText("管家婆商品信息更新")
  const disclosure = container.querySelector("details")!
  expect(disclosure).not.toHaveAttribute("open")
  expect(disclosure.querySelector("pre")).toHaveClass(
    "max-h-60",
    "overflow-auto"
  )
  expect(disclosure.parentElement!.querySelector("p")).toHaveClass(
    "line-clamp-2"
  )
  await user.click(screen.getByRole("button", { name: "查看运行历史" }))
  await screen.findByText("最近 1 次执行")
  expect(mocks.listHistory).toHaveBeenCalledWith(run.task_name)
  expect(container.querySelectorAll("details")).toHaveLength(2)
  for (const details of container.querySelectorAll("details")) {
    expect(details).not.toHaveAttribute("open")
    expect(details.querySelector("pre")!.textContent).toBe(longError)
  }
})

test("uses bounded disclosures for business-date failures too", async () => {
  const user = userEvent.setup()
  const { container } = render(<ScheduledTaskPage />)
  await screen.findByText("管家婆商品信息更新")
  await user.click(screen.getByRole("button", { name: "业务日期状态" }))
  await waitFor(() => expect(mocks.listBusiness).toHaveBeenCalled())
  await screen.findByText("import_gj_merged_product_info_daily")
  const disclosure = container.querySelector("details")!
  expect(disclosure).not.toHaveAttribute("open")
  await user.click(within(disclosure).getByText("查看详情"))
  expect(disclosure).toHaveAttribute("open")
  expect(disclosure.querySelector("pre")!.textContent).toBe(longError)
})
