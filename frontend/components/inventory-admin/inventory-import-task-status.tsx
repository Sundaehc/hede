import { CircleAlert, LoaderCircle, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type InventoryImportTaskNotice = {
  phase:
    | "submitting"
    | "restoring"
    | "queued"
    | "running"
    | "disconnected"
    | "not-found"
  filename?: string
}

const PHASE_LABELS = {
  submitting: "正在提交文件",
  restoring: "正在恢复核验",
  queued: "等待后台处理",
  running: "正在导入",
  disconnected: "连接暂时中断",
  "not-found": "批次待确认",
}

export function InventoryImportTaskStatus({
  notice,
  taskId,
  isChecking,
  onCheck,
  onViewDetails,
}: {
  notice: InventoryImportTaskNotice
  taskId: string
  isChecking: boolean
  onCheck: () => void
  onViewDetails?: () => void
}) {
  const uncertain =
    notice.phase === "disconnected" || notice.phase === "not-found"
  const description = {
    submitting: "正在提交导入任务，请勿刷新或关闭页面；此时文件尚未确认接收。",
    restoring: "正在恢复并核验上次导入结果，请勿重复导入。",
    queued: "文件已接收，等待后台处理；完成后自动刷新列表，请勿重复提交。",
    running:
      "后台正在导入" +
      (notice.filename ? "「" + notice.filename + "」" : "") +
      "，完成后自动刷新列表。",
    disconnected:
      "连接暂时中断，正在自动核验导入结果；这不代表导入失败，请勿重复提交。",
    "not-found":
      "暂未查到该批次，仍在核验提交结果；请先恢复连接或联系管理员核对，不要重新上传。",
  }[notice.phase]

  return (
    <section
      aria-label="导入任务状态"
      className={cn(
        "rounded-xl border bg-card p-4 shadow-xs",
        uncertain
          ? "border-amber-500/35 bg-amber-500/5"
          : "border-primary/20 bg-primary/5"
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="flex min-w-0 flex-1 gap-3">
          <span
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background",
              uncertain
                ? "border-amber-500/25 text-amber-700 dark:text-amber-400"
                : "border-primary/20 text-primary"
            )}
          >
            {uncertain ? (
              <CircleAlert className="size-4" aria-hidden="true" />
            ) : (
              <LoaderCircle
                className="size-4 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            )}
          </span>
          <div
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className="min-w-0 space-y-1"
          >
            <h3 className="text-sm font-semibold">
              {PHASE_LABELS[notice.phase]}
            </h3>
            <p className="text-xs leading-5 break-words text-muted-foreground">
              {description}
            </p>
          </div>
        </div>
        {taskId && (
          <div className="flex shrink-0 items-center gap-2 pl-12 sm:pl-0">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCheck}
              disabled={isChecking}
              aria-label="立即核验"
              className="h-8 gap-1.5 bg-background text-xs"
            >
              <RefreshCw
                className={cn(
                  "size-3.5",
                  isChecking && "animate-spin motion-reduce:animate-none"
                )}
                aria-hidden="true"
              />
              {isChecking ? "核验中" : "立即核验"}
            </Button>
            {onViewDetails && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onViewDetails}
                className="h-8 text-xs"
              >
                查看详情
              </Button>
            )}
          </div>
        )}
      </div>
      {!onViewDetails && (
        <div className="mt-3 space-y-1.5 border-t border-border/60 pt-3 text-xs leading-5 text-muted-foreground sm:ml-12">
          {taskId && (
            <p>每 3 秒自动核验；“立即核验”只查询结果，不会重新导入。</p>
          )}
          {notice.phase !== "submitting" && (
            <p>
              可关闭弹窗继续使用页面；同一标签页刷新或返回可恢复结果查询，请勿清除存储或关闭标签页。
            </p>
          )}
          <p>当前仅支持结果核验，不支持文件断点续传或后端重启后续跑。</p>
          {taskId && (
            <p className="break-all">
              批次编号：
              <span className="font-mono text-[11px] text-foreground/75 select-all">
                {taskId}
              </span>
            </p>
          )}
        </div>
      )}
    </section>
  )
}
