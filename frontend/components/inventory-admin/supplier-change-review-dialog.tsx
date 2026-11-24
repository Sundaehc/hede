"use client"

import { useEffect, useRef, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Inbox,
  LoaderCircle,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  listSupplierChanges,
  reviewSupplierChange,
  type SupplierBrandItem,
  type SupplierChangeStatus,
} from "@/lib/api"
import { cn } from "@/lib/utils"

type ReviewFilter = SupplierChangeStatus | "all"

const labels = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
  all: "全部",
} satisfies Record<ReviewFilter, string>
const filters: ReviewFilter[] = ["pending", "approved", "rejected", "all"]
const emptyTitles: Record<ReviewFilter, string> = {
  pending: "暂无待审核申请",
  approved: "暂无已通过申请",
  rejected: "暂无已驳回申请",
  all: "暂无变更申请",
}
const statusStyles: Record<SupplierChangeStatus, string> = {
  pending: "border-border bg-secondary text-secondary-foreground",
  approved: "border-border bg-card text-foreground",
  rejected: "border-destructive/20 bg-destructive/8 text-destructive",
}
const dateTime = new Intl.DateTimeFormat("zh-CN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Shanghai",
})

export function SupplierChangeReviewDialog({
  userId,
  brands,
  onClose,
  onApproved,
}: {
  userId: number
  brands: ReadonlyArray<Pick<SupplierBrandItem, "code" | "name">>
  onClose: () => void
  onApproved: () => void
}) {
  const [status, setStatus] = useState<ReviewFilter>("pending")
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof listSupplierChanges>
  > | null>(null)
  const [canReview, setCanReview] = useState<boolean | null>(null)
  const [loadError, setLoadError] = useState("")
  const [notice, setNotice] = useState("")
  const [action, setAction] = useState<{
    id: number
    decision: "approve" | "reject"
  } | null>(null)
  const [note, setNote] = useState("")
  const [failure, setFailure] = useState("")
  const [saving, setSaving] = useState(false)
  const busy = useRef(false)
  const listBody = useRef<HTMLDivElement>(null)
  const allFilterButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    listSupplierChanges(status, page, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        if (page > 1 && !data.items.length) {
          setPage(Math.max(1, Math.ceil(data.total / data.page_size)))
          return
        }
        setCanReview(data.can_review)
        setResult(data)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setLoadError(error instanceof Error ? error.message : "读取申请失败")
      })
    return () => controller.abort()
  }, [status, page, revision])

  function resetList() {
    if (listBody.current) listBody.current.scrollTop = 0
    setResult(null)
    setLoadError("")
    setAction(null)
    setFailure("")
  }

  function selectFilter(next: ReviewFilter) {
    if (next === status) return
    resetList()
    setStatus(next)
    setPage(1)
  }

  function selectAction(id: number, decision: "approve" | "reject") {
    setAction({ id, decision })
    setNote("")
    setFailure("")
  }

  async function submit() {
    if (
      !action ||
      busy.current ||
      (action.decision === "reject" && !note.trim())
    )
      return
    busy.current = true
    setSaving(true)
    setFailure("")
    try {
      const response = await reviewSupplierChange(
        action.id,
        action.decision,
        note.trim()
      )
      if (action.decision === "approve") onApproved()
      resetList()
      setNotice(`#${action.id} · ${response.message}`)
      setRevision((value) => value + 1)
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "审核失败，请重试")
    } finally {
      busy.current = false
      setSaving(false)
    }
  }

  const valueLabel = (field: string, value: string | null) =>
    field === "brand"
      ? brands.find((item) => item.code === value)?.name || value || "—"
      : value || "—"
  const pages = result
    ? Math.max(1, Math.ceil(result.total / result.page_size))
    : 1

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy.current) onClose()
      }}
    >
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden p-0 sm:max-h-[90dvh] sm:max-w-3xl">
        <DialogHeader className="shrink-0 flex-row items-start gap-3 border-b border-border/70 bg-card px-4 py-4 sm:gap-4 sm:px-6 sm:py-5">
          <div className="grid size-10 shrink-0 place-items-center rounded-xl border bg-secondary text-secondary-foreground sm:size-11">
            <ClipboardCheck className="size-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <DialogTitle>供应商变更审核</DialogTitle>
            <DialogDescription className="text-xs leading-5 sm:text-sm">
              供应商已有费用单据时，资料变更须经商品组审核后才生效。
            </DialogDescription>
          </div>
          <DialogClose
            aria-label="关闭"
            disabled={saving}
            className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-lg text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="size-4" aria-hidden="true" />
          </DialogClose>
        </DialogHeader>

        <div className="flex shrink-0 flex-col gap-3 border-b border-border/70 bg-card px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:px-6">
          <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {canReview === null
              ? "变更申请"
              : canReview
                ? "商品组审核队列"
                : "我的变更申请"}
            {result ? (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">
                {result.total} 条
              </span>
            ) : null}
          </h3>
          <div
            role="group"
            aria-label="申请状态"
            className="grid grid-cols-4 gap-0.5 rounded-xl border border-border/60 bg-muted p-1"
          >
            {filters.map((filter) => (
              <button
                key={filter}
                ref={filter === "all" ? allFilterButton : undefined}
                type="button"
                aria-pressed={status === filter}
                disabled={saving}
                className={cn(
                  "min-w-0 cursor-pointer rounded-lg px-1 py-1.5 text-xs font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 sm:px-3",
                  status === filter
                    ? "bg-card text-foreground shadow-xs ring-1 ring-border/60"
                    : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
                )}
                onClick={() => selectFilter(filter)}
              >
                {labels[filter]}
              </button>
            ))}
          </div>
        </div>

        <div
          ref={listBody}
          className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6"
        >
          {notice ? (
            <p
              role="status"
              className="flex items-start gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm"
            >
              <ClipboardCheck
                className="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span className="min-w-0 [overflow-wrap:anywhere]">{notice}</span>
            </p>
          ) : null}
          {loadError ? (
            <div
              role="alert"
              className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm"
            >
              <CircleAlert
                className="size-4 shrink-0 text-destructive"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                <p className="font-medium">读取变更申请失败</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {loadError}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  resetList()
                  setRevision((value) => value + 1)
                }}
              >
                重试
              </Button>
            </div>
          ) : !result ? (
            <div
              role="status"
              className="flex min-h-44 items-center justify-center gap-2 rounded-xl border bg-muted/45 px-4 text-sm text-muted-foreground"
            >
              <LoaderCircle
                className="size-4 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
              正在加载申请…
            </div>
          ) : !result.items.length ? (
            <div className="flex min-h-44 flex-col items-center justify-center gap-3 rounded-xl border border-border/70 bg-muted/45 px-4 py-5 text-center">
              <div className="grid size-10 place-items-center rounded-xl border bg-card text-muted-foreground shadow-xs">
                <Inbox className="size-5" aria-hidden="true" />
              </div>
              <div role="status" className="space-y-1">
                <p className="text-sm font-semibold">{emptyTitles[status]}</p>
                <p className="text-xs leading-5 text-muted-foreground">
                  {status !== "all"
                    ? "可查看全部申请，了解其他状态的处理进度。"
                    : canReview
                      ? "新提交的供应商变更申请会显示在这里。"
                      : "提交供应商资料变更后，可在这里跟踪审核进度。"}
                </p>
              </div>
              {status !== "all" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    allFilterButton.current?.focus()
                    selectFilter("all")
                  }}
                >
                  查看全部
                  <ChevronRight className="size-3.5" aria-hidden="true" />
                </Button>
              ) : null}
            </div>
          ) : (
            <ul className="space-y-3">
              {result.items.map((item) => {
                const canDecide =
                  result.can_review &&
                  item.status === "pending" &&
                  item.requester_id !== userId
                const editing = action?.id === item.id
                return (
                  <li
                    key={item.id}
                    className="min-w-0 space-y-3 rounded-xl border bg-card p-3.5 sm:p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold [overflow-wrap:anywhere]">
                          {item.supplier_name}{" "}
                          <span className="text-xs font-normal text-muted-foreground">
                            #{item.id}
                          </span>
                        </p>
                        <p className="mt-1 text-xs leading-5 [overflow-wrap:anywhere] text-muted-foreground">
                          {valueLabel("brand", item.supplier_brand)}
                          {item.supplier_factory_code &&
                            ` · 工厂代码 ${item.supplier_factory_code}`}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                          statusStyles[item.status]
                        )}
                      >
                        <span
                          className="size-1.5 rounded-full bg-current"
                          aria-hidden="true"
                        />
                        {labels[item.status]}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-baseline gap-x-3 text-xs leading-5 text-muted-foreground">
                      <span className="min-w-0 [overflow-wrap:anywhere]">
                        申请人：{item.requester_name}
                      </span>
                      <time dateTime={item.created_at}>
                        {dateTime.format(new Date(item.created_at))}
                      </time>
                      <span>涉及 {item.expense_document_count} 张费用单据</span>
                    </div>
                    <div className="overflow-hidden rounded-lg border border-border/75">
                      <table
                        aria-label={`申请 #${item.id} 的修改内容`}
                        className="w-full table-fixed text-sm"
                      >
                        <thead className="bg-muted/65 text-xs text-muted-foreground">
                          <tr>
                            <th
                              scope="col"
                              className="w-[29%] px-2 py-2 text-left font-medium sm:w-1/4 sm:px-3"
                            >
                              字段
                            </th>
                            <th
                              scope="col"
                              className="px-2 py-2 text-left font-medium sm:px-3"
                            >
                              原值
                            </th>
                            <th
                              scope="col"
                              className="border-l border-border/60 px-2 py-2 text-left font-semibold text-foreground sm:px-3"
                            >
                              申请值
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {item.changes.map((change) => (
                            <tr key={change.field}>
                              <th
                                scope="row"
                                className="px-2 py-2 text-left align-top text-xs font-medium [overflow-wrap:anywhere] sm:px-3"
                              >
                                {change.label}
                              </th>
                              <td className="px-2 py-2 align-top [overflow-wrap:anywhere] text-muted-foreground sm:px-3">
                                {valueLabel(change.field, change.before)}
                              </td>
                              <td className="border-l border-border/60 bg-muted/30 px-2 py-2 align-top font-medium [overflow-wrap:anywhere] sm:px-3">
                                {valueLabel(change.field, change.after)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {item.reviewer_name && (
                      <p className="rounded-lg bg-muted/55 px-3 py-2 text-xs leading-5 [overflow-wrap:anywhere] text-muted-foreground">
                        审核人：{item.reviewer_name}
                        {item.reviewed_at &&
                          ` · ${dateTime.format(new Date(item.reviewed_at))}`}
                        {item.review_note && ` · ${item.review_note}`}
                      </p>
                    )}
                    {canDecide && !editing && (
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={saving}
                          onClick={() => selectAction(item.id, "reject")}
                        >
                          驳回申请
                        </Button>
                        <Button
                          size="sm"
                          disabled={saving}
                          onClick={() => selectAction(item.id, "approve")}
                        >
                          审核通过
                        </Button>
                      </div>
                    )}
                    {editing && (
                      <form
                        className="space-y-2.5 rounded-lg border bg-muted/40 p-3"
                        onSubmit={(event) => {
                          event.preventDefault()
                          void submit()
                        }}
                      >
                        <p className="text-sm font-medium">
                          {action.decision === "approve"
                            ? "通过后将立即更新供应商资料"
                            : "驳回后保留原供应商资料"}
                        </p>
                        <label className="block space-y-1.5">
                          <span className="block text-xs font-medium">
                            {action.decision === "reject"
                              ? "驳回原因（必填）"
                              : "审核备注（选填）"}
                          </span>
                          <textarea
                            className="block min-h-20 w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                            aria-label={
                              action.decision === "reject"
                                ? "驳回原因"
                                : "审核备注"
                            }
                            placeholder={
                              action.decision === "reject"
                                ? "填写驳回原因"
                                : "填写审核备注"
                            }
                            value={note}
                            maxLength={1000}
                            required={action.decision === "reject"}
                            disabled={saving}
                            onChange={(event) => setNote(event.target.value)}
                          />
                        </label>
                        {failure && (
                          <p role="alert" className="text-sm text-destructive">
                            {failure}
                          </p>
                        )}
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={saving}
                            onClick={() => setAction(null)}
                          >
                            取消
                          </Button>
                          <Button
                            size="sm"
                            type="submit"
                            variant={
                              action.decision === "reject"
                                ? "destructive"
                                : "default"
                            }
                            disabled={
                              saving ||
                              (action.decision === "reject" && !note.trim())
                            }
                          >
                            {saving
                              ? "正在提交…"
                              : action.decision === "approve"
                                ? "确认通过"
                                : "确认驳回"}
                          </Button>
                        </div>
                      </form>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
        {pages > 1 ? (
          <nav
            aria-label="申请分页"
            className="flex shrink-0 items-center justify-between gap-2 border-t border-border/70 bg-card px-4 py-2.5 text-xs text-muted-foreground sm:justify-end sm:gap-3 sm:px-6"
          >
            <Button
              size="sm"
              variant="outline"
              disabled={saving || page <= 1}
              onClick={() => {
                resetList()
                setPage(page - 1)
              }}
            >
              <ChevronLeft className="size-3.5" aria-hidden="true" />
              上一页
            </Button>
            <span className="tabular-nums">
              {page} / {pages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={saving || page >= pages}
              onClick={() => {
                resetList()
                setPage(page + 1)
              }}
            >
              下一页
              <ChevronRight className="size-3.5" aria-hidden="true" />
            </Button>
          </nav>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
