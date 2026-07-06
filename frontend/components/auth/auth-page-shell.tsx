"use client"

import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { Activity, BadgeCheck, Building2, FileSpreadsheet } from "lucide-react"

import { ThemeToggle } from "@/components/theme-toggle"


type AuthPageShellProps = {
  title: string
  description: string
  icon: LucideIcon
  children: ReactNode
  footer: ReactNode
}

const systemItems = [
  { icon: FileSpreadsheet, label: "商品资料", value: "档案 / 精细表" },
  { icon: Building2, label: "业务单据", value: "进销存 / 采购单" },
  { icon: Activity, label: "操作留痕", value: "按账号记录" },
]

export function AuthPageShell({ title, description, icon: Icon, children, footer }: AuthPageShellProps) {
  return (
    <div className="relative min-h-svh overflow-hidden bg-background px-4 py-5 text-foreground sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-emerald-500/55 to-transparent" />
      <div className="absolute right-4 top-4 z-10 sm:right-6">
        <ThemeToggle />
      </div>

      <div className="mx-auto grid min-h-[calc(100svh-2.5rem)] w-full max-w-6xl items-center gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
        <section className="hidden max-w-xl lg:block">
          <div className="space-y-4">
            <h1 className="text-4xl font-semibold tracking-normal text-foreground">赫德商品运营中台</h1>
            <p className="max-w-md text-sm leading-6 text-muted-foreground">
              账号按部门分配权限，登录后进入对应的商品、经营、采购和管理工作区。
            </p>
          </div>

          <div className="mt-10 grid max-w-lg grid-cols-3 overflow-hidden rounded-2xl border border-border bg-card/85 shadow-sm backdrop-blur">
            {systemItems.map((item, index) => {
              const ItemIcon = item.icon
              return (
                <div key={item.label} className={index === 0 ? "p-4" : "border-l border-border p-4"}>
                  <ItemIcon className="mb-3 size-4 text-foreground" />
                  <div className="text-xs font-medium text-foreground">{item.label}</div>
                  <div className="mt-1 text-[11px] text-muted-foreground">{item.value}</div>
                </div>
              )
            })}
          </div>
        </section>

        <section className="w-full max-w-md justify-self-center lg:justify-self-end">
          <div className="mb-4 flex items-center gap-3 pr-12 lg:hidden">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <BadgeCheck className="size-4" />
            </div>
            <div>
              <div className="text-sm font-semibold">赫德商品运营中台</div>
              <div className="text-xs text-muted-foreground">按部门进入对应工作区</div>
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-border bg-card/95 shadow-lg shadow-black/[0.04] backdrop-blur">
            <div className="border-b border-border bg-muted/25 px-6 py-5">
              <div className="flex items-start gap-3">
                <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
                  <Icon className="size-5" />
                </div>
                <div className="min-w-0">
                  <h2 className="text-xl font-semibold tracking-normal">{title}</h2>
                  <p className="mt-1 text-sm leading-5 text-muted-foreground">{description}</p>
                </div>
              </div>
            </div>

            <div className="px-6 py-5">{children}</div>

            <div className="border-t border-border bg-muted/20 px-6 py-4 text-center text-xs text-muted-foreground">
              {footer}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
