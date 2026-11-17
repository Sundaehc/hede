import type { ReactNode } from "react"
import {
  ArrowUpRight,
  Check,
  LoaderCircle,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

export function StockStatusCard({
  label,
  value,
  description,
  icon: Icon,
  active,
  tone = "neutral",
  onClick,
  children,
}: {
  label: string
  value: string | number
  description: string
  icon: LucideIcon
  active: boolean
  tone?: "neutral" | "warning" | "danger"
  onClick: () => void
  children?: ReactNode
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col overflow-hidden rounded-2xl border bg-card/75 shadow-xs backdrop-blur-xl transition-colors",
        active
          ? "border-primary/40 bg-primary/5"
          : "border-border/80 hover:border-primary/25",
        active && tone === "warning" && "border-amber-500/50 bg-amber-500/5",
        active && tone === "danger" && "border-destructive/40 bg-destructive/5"
      )}
    >
      <button
        type="button"
        aria-pressed={active}
        onClick={onClick}
        className="group flex flex-1 cursor-pointer flex-col p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset sm:px-5"
      >
        <span className="flex w-full items-center justify-between gap-2">
          <span className="text-xs font-medium text-muted-foreground sm:text-sm">
            {label}
          </span>
          <Icon
            aria-hidden="true"
            className={cn(
              "size-4 shrink-0 text-muted-foreground/70",
              tone === "warning" && "text-amber-600 dark:text-amber-400",
              tone === "danger" && "text-destructive"
            )}
          />
        </span>
        <span className="mt-3 flex w-full items-end justify-between gap-2">
          <span className="text-3xl leading-none font-semibold tracking-tight tabular-nums">
            {value}
            <span className="ml-1.5 text-xs font-normal text-muted-foreground">
              项
            </span>
          </span>
          {active ? (
            <Check className="size-4 text-foreground" aria-hidden="true" />
          ) : (
            <ArrowUpRight
              className="size-4 text-muted-foreground/50 transition-colors group-hover:text-foreground"
              aria-hidden="true"
            />
          )}
        </span>
        <span className="mt-2.5 text-xs leading-5 text-muted-foreground">
          {description}
        </span>
      </button>
      {children}
    </div>
  )
}

export function StockListState({
  icon: Icon,
  title,
  description,
  loading = false,
  children,
}: {
  icon: LucideIcon
  title: string
  description: ReactNode
  loading?: boolean
  children?: ReactNode
}) {
  return (
    <div className="flex min-h-80 flex-col items-center justify-center bg-linear-to-b from-muted/15 to-transparent px-5 py-12 text-center sm:min-h-88">
      <div className="mb-5 flex size-16 items-center justify-center rounded-2xl border border-border/80 bg-card/80 shadow-xs ring-6 ring-muted/30">
        {loading ? (
          <LoaderCircle
            className="size-7 animate-spin text-muted-foreground motion-reduce:animate-none"
            aria-hidden="true"
          />
        ) : (
          <Icon className="size-7 text-muted-foreground" aria-hidden="true" />
        )}
      </div>
      <h3
        className="max-w-lg text-base leading-7 font-semibold"
        role={loading ? "status" : undefined}
      >
        {title}
      </h3>
      <div className="mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
        {description}
      </div>
      {children && (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {children}
        </div>
      )}
    </div>
  )
}
