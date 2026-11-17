import { CalendarDays } from "lucide-react"
import type { ProductGoodsResponse } from "@/lib/types"

export function GoodsSalesSourceStatus({
  status,
}: {
  status: ProductGoodsResponse["sales_source_status"]
}) {
  if (!status) return null
  return (
    <div
      className="rounded-xl border border-border bg-card/75 px-4 py-3 text-xs leading-6 text-muted-foreground"
      aria-label="销量数据口径"
    >
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <span className="flex items-center gap-2 font-medium text-foreground">
          <CalendarDays className="size-3.5" aria-hidden="true" />
          近30天：
          {status.window_start && status.window_end
            ? `${status.window_start} 至 ${status.window_end}`
            : "暂无可用日销"}
        </span>
        <span>聚水潭截至 {status.jst_latest_date ?? "无数据"}</span>
        <span>唯品截至 {status.vip_latest_date ?? "无数据"}</span>
      </div>
      {status.delayed_sources.length > 0 && (
        <p role="status" className="mt-1 text-amber-700 dark:text-amber-400">
          {status.delayed_sources
            .map((source) => (source === "jst" ? "聚水潭" : "唯品"))
            .join("、")}
          日销尚未更新至 {status.expected_date}，以上为实际统计范围。
        </p>
      )}
      <p>
        渠道销量“—”表示该统计期内无匹配记录或数据不可用，不能直接视为零销量；明确的
        0 表示匹配记录汇总为零。
      </p>
    </div>
  )
}
