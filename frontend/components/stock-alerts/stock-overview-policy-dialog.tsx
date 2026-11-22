"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { saveStockOverviewPolicy } from "@/lib/api"
import type { ExitPolicy } from "@/lib/stock-overview"

const scopeKey = ({ year, season }: Pick<ExitPolicy, "year" | "season">) =>
  JSON.stringify([year, season])
const emptyPolicy = ({
  year,
  season,
}: Pick<ExitPolicy, "year" | "season">): ExitPolicy => ({
  year,
  season,
  sale_start: null,
  exit_date: "",
  lead_days: 30,
  target_rate: 100,
  channel: "",
  version: 0,
})

export function StockOverviewPolicyDialog({
  brand,
  brandLabel,
  scopes,
  policies,
  close,
  saved,
}: {
  brand: string
  brandLabel: string
  scopes: Array<Pick<ExitPolicy, "year" | "season">>
  policies: ExitPolicy[]
  close: () => void
  saved: () => void
}) {
  const currentScopes = scopes.filter(({ year }) =>
    /^(20|21)[0-9]{2}$/.test(year)
  )
  const resolve = (scope: Pick<ExitPolicy, "year" | "season">) =>
    policies.find((rule) => scopeKey(rule) === scopeKey(scope)) ??
    emptyPolicy(scope)
  const [policy, setPolicy] = useState(() =>
    currentScopes[0] ? resolve(currentScopes[0]) : null
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const update = (values: Partial<ExitPolicy>) =>
    setPolicy((item) => (item ? { ...item, ...values } : null))
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) close()
      }}
    >
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>设置清货退出规则</DialogTitle>
          <DialogDescription>
            {brandLabel} ·
            按款式年份和季节设置。规则保存后同范围的款会重新计算建议。
          </DialogDescription>
        </DialogHeader>
        {!policy ? (
          <p className="py-5 text-sm text-muted-foreground">
            当前库存未匹配到有效的款式年份与季节，请先完善商品档案。
          </p>
        ) : (
          <form
            className="space-y-4"
            onSubmit={async (event) => {
              event.preventDefault()
              if (busy) return
              setBusy(true)
              setError(null)
              try {
                await saveStockOverviewPolicy({ brand, ...policy })
                saved()
              } catch (cause) {
                setError(
                  cause instanceof Error ? cause.message : "保存失败，请重试"
                )
              } finally {
                setBusy(false)
              }
            }}
          >
            <label className="grid gap-1.5 text-sm">
              款式年份 / 季节
              <Select
                value={scopeKey(policy)}
                disabled={busy}
                onChange={(event) => {
                  const scope = currentScopes.find(
                    (item) => scopeKey(item) === event.target.value
                  )
                  if (scope) {
                    setPolicy(resolve(scope))
                    setError(null)
                  }
                }}
              >
                {currentScopes.map((scope) => (
                  <option key={scopeKey(scope)} value={scopeKey(scope)}>
                    {scope.year} 年 · {scope.season}
                    {policies.some((rule) => scopeKey(rule) === scopeKey(scope))
                      ? "（已设置）"
                      : ""}
                  </option>
                ))}
              </Select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm">
                再次开售日（可选）
                <Input
                  type="date"
                  value={policy.sale_start ?? ""}
                  max={policy.exit_date || undefined}
                  disabled={busy}
                  onChange={(event) =>
                    update({ sale_start: event.target.value || null })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                计划退出日
                <Input
                  type="date"
                  value={policy.exit_date}
                  min={policy.sale_start ?? undefined}
                  required
                  disabled={busy}
                  onChange={(event) =>
                    update({ exit_date: event.target.value })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                提前多少天提示
                <Input
                  type="number"
                  min={1}
                  max={365}
                  value={policy.lead_days || ""}
                  required
                  disabled={busy}
                  onChange={(event) =>
                    update({ lead_days: Number(event.target.value) })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                目标参考售罄率（%）
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={policy.target_rate || ""}
                  required
                  disabled={busy}
                  onChange={(event) =>
                    update({ target_rate: Number(event.target.value) })
                  }
                />
              </label>
            </div>
            <label className="grid gap-1.5 text-sm">
              拟用清货渠道
              <Input
                required
                placeholder="例如：达播清仓"
                value={policy.channel}
                maxLength={100}
                disabled={busy}
                onChange={(event) => update({ channel: event.target.value })}
              />
            </label>
            <p className="rounded-lg bg-muted/50 px-3 py-2 text-xs leading-5 text-muted-foreground">
              100% 表示退出时清完当前可售库存；低于 100%
              时，需有完整销售和有效历史入库参考才能计算。再次开售日用于标记跨季待售。
            </p>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={close}
                disabled={busy}
              >
                取消
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? "正在保存…" : "保存规则"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
