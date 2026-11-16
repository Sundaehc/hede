"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { BellRing } from "lucide-react"
import { useAuth } from "@/components/auth/auth-provider"
import { getStockAlertTaskReminders } from "@/lib/api"
import { useTaskRefresh } from "./use-task-refresh"

export function StockAlertTaskReminder() {
  const { user, hasPermission } = useAuth()
  if (!user || !hasPermission("product.view")) return null
  return <TaskReminderContent key={user.id} />
}

function TaskReminderContent() {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{
    open: number
    overdue: number
    error: boolean
  } | null>(null)
  const refresh = useCallback(() => setRevision((value) => value + 1), [])
  useTaskRefresh(refresh)
  useEffect(() => {
    const controller = new AbortController()
    getStockAlertTaskReminders(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setState({ ...result, error: false })
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setState((old) => ({
            open: old?.open ?? 0,
            overdue: old?.overdue ?? 0,
            error: true,
          }))
      })
    return () => controller.abort()
  }, [revision])
  if (!state || (!state.open && !state.error)) return null
  const label = state.error
    ? "预警提醒暂不可用，点击查看待办"
    : `我的预警待办 ${state.open} 项${state.overdue ? `，已超期 ${state.overdue} 项` : ""}`
  return (
    <Link
      href="/stock-alerts/tasks?view=mine-open"
      scroll={false}
      title={label}
      aria-label={label}
      className="mx-2 mt-3 flex items-center justify-center gap-2 rounded-xl border border-sidebar-border bg-sidebar-accent px-2 py-2.5 text-xs text-sidebar-foreground md:mx-3 md:justify-start md:px-3"
    >
      <BellRing className="size-4 shrink-0 text-amber-400" aria-hidden="true" />
      <span role="status" className="hidden min-w-0 md:block">
        <span className="block font-medium">
          {state.error ? "预警提醒暂不可用" : `我的预警待办 · ${state.open}`}
        </span>
        <span className="mt-1 block text-sidebar-foreground/70">
          {state.error
            ? "点击查看，稍后自动重试"
            : state.overdue
              ? `已超期 ${state.overdue} 项，请及时处理`
              : "查看负责人分配的处理事项"}
        </span>
      </span>
      <span className="md:hidden">{state.error ? "!" : state.open}</span>
    </Link>
  )
}
