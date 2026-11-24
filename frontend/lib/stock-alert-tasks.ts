import type { StockAlertItem, StockAlertKind } from "./stock-alerts"

export const taskStatusLabels = {
  pending: "待处理",
  processing: "处理中",
  completed: "已完成",
}
export const alertKindLabels = {
  zero: "新品零动销",
  slow: "低售罄、滞销",
  replenish: "核心尺码补货",
  clearance: "清货跟进",
}
export type StockTaskKind = keyof typeof alertKindLabels
export type StockAlertTaskSummary = {
  id: number
  status: keyof typeof taskStatusLabels
  assignee_name: string
  due_date: string
  overdue: boolean
}
export type StockAlertTask = StockAlertTaskSummary & {
  image_url?: string | null
  brand: string
  product_id: number
  kind: StockTaskKind
  sku: string
  original_sku: string | null
  product_name: string | null
  color: string | null
  snapshot: Partial<Omit<StockAlertItem, "available_quantity">> & {
    reason?: string
    quantity?: number | null
    sizes?: Array<{ name: string; available: number; quantity: number }>
    channel?: string | null
    exit_date?: string | null
    available_quantity?: string | number
    stock_date: string | null
    sales_end: string | null
  }
  assignee_id: number
  measures: string
  result: string
  version: number
  created_at: string
  updated_at: string
  completed_at: string | null
}
export type TaskAssignee = { id: number; name: string; department: string }
export type TaskFilters = {
  scope: "mine" | "all"
  status: "open" | "overdue" | "completed" | "all"
  brand: string
  kind: "" | StockTaskKind
  query: string
  page: number
}
export type TaskListResponse = {
  items: StockAlertTask[]
  total: number
  counts: { open: number; overdue: number; completed: number }
  page: number
  page_size: number
  today: string
}
export type TaskEvent = {
  id: number
  actor_name: string
  action: "created" | "updated" | "completed"
  changes: Partial<
    Pick<
      StockAlertTask,
      | "assignee_id"
      | "assignee_name"
      | "due_date"
      | "status"
      | "measures"
      | "result"
    >
  >
  created_at: string
}
export type TaskEventsResponse = {
  items: TaskEvent[]
  page: number
  page_size: number
  total: number
}
export type TaskCreate = {
  brand: string
  product_id: number
  kind: StockAlertKind
  assignee_id: number
  due_date: string
  measures: string
}
export type TaskUpdate = { version: number } & Partial<
  Pick<
    StockAlertTask,
    "assignee_id" | "due_date" | "status" | "measures" | "result"
  >
>

export type TaskBatchResult<Key extends string | number = number> = {
  total: number
  succeeded: Key[]
  failed: Array<{ id: Key; label: string; reason: string }>
}
export type TaskBatchCreate = Omit<TaskCreate, "product_id"> & {
  product_ids: number[]
}
export type TaskBatchUpdate = {
  items: Array<{ id: number; version: number }>
  changes: Omit<TaskUpdate, "version">
}

export function beijingDate(offsetDays = 0) {
  return new Date(Date.now() + (8 + offsetDays * 24) * 3600_000)
    .toISOString()
    .slice(0, 10)
}

export function taskDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value))
}
