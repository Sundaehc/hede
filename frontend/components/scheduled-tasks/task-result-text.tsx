"use client"

import { cn } from "@/lib/utils"

const PREVIEW_MAX_CHARS = 220

export function TaskResultText({
  value,
  className,
}: {
  value: string
  className?: string
}) {
  const compact = value.replace(/\s+/g, " ").trim()
  const preview =
    compact.length > PREVIEW_MAX_CHARS
      ? `${compact.slice(0, PREVIEW_MAX_CHARS)}…`
      : compact
  const hasDetails = compact.length > PREVIEW_MAX_CHARS || value.includes("\n")

  return (
    <div className={cn("max-w-full min-w-0 text-xs leading-5", className)}>
      <p className="line-clamp-2 break-all">{preview || "-"}</p>
      {hasDetails ? (
        <details className="group/result mt-1">
          <summary className="w-fit cursor-pointer rounded text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
            <span className="group-open/result:hidden">查看详情</span>
            <span className="hidden group-open/result:inline">收起详情</span>
          </summary>
          <pre className="mt-2 max-h-60 max-w-full overflow-auto rounded-md border border-border bg-muted/40 p-2 font-mono text-[11px] leading-5 break-all whitespace-pre-wrap">
            {value}
          </pre>
        </details>
      ) : null}
    </div>
  )
}
