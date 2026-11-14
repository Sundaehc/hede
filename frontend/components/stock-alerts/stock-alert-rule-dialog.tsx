"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { saveStockAlertRule } from "@/lib/api"
import type { StockAlertKind, StockAlertRule } from "@/lib/stock-alerts"

export function StockAlertRuleDialog({
  brand,
  brandLabel,
  season,
  kind,
  rule,
  onClose,
  onSaved,
}: {
  brand: string
  brandLabel: string
  season: string
  kind: StockAlertKind
  rule: StockAlertRule
  onClose: () => void
  onSaved: () => void
}) {
  const [days, setDays] = useState(String(rule.age_days))
  const [rate, setRate] = useState(rule.rate)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            设置{kind === "zero" ? "新品零动销" : "低售罄、滞销"}规则
          </DialogTitle>
          <DialogDescription>
            规则保存后对所有有查看权限的账户生效。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (saving) return
            setSaving(true)
            setError(null)
            try {
              await saveStockAlertRule({
                brand,
                season,
                kind,
                age_days: Number(days),
                rate,
                version: rule.version,
              })
              onSaved()
            } catch (cause) {
              setError(
                cause instanceof Error ? cause.message : "规则保存失败，请重试"
              )
            } finally {
              setSaving(false)
            }
          }}
        >
          <div className="rounded-lg border bg-muted/30 p-3 text-sm">
            <span className="text-muted-foreground">规则范围</span>
            <p className="mt-1 font-medium">
              {brandLabel} · {season || "全部季节（通用规则）"}
            </p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              季节专属规则优先于品牌通用规则；未设置时使用默认规则。范围取当前已查询的品牌和季节。
            </p>
          </div>
          <label className="block space-y-2 text-sm">
            <span>上市满多少天</span>
            <Input
              aria-label="上市天数"
              type="number"
              required
              min={1}
              max={3650}
              value={days}
              disabled={saving}
              onChange={(event) => setDays(event.target.value)}
            />
          </label>
          {kind === "slow" && (
            <label className="block space-y-2 text-sm">
              <span>参考售罄率低于（%）</span>
              <Input
                aria-label="售罄率阈值"
                type="number"
                required
                min={0}
                max={100}
                step="0.01"
                value={rate}
                disabled={saving}
                onChange={(event) => setRate(event.target.value)}
              />
            </label>
          )}
          <p className="text-xs leading-6 text-muted-foreground">
            {kind === "zero"
              ? "同时要求有可售库存、上市后销售数量为 0。销售后退回不计为从未销售。"
              : "同时要求有可售库存。参考售罄率＝上市后净销量 ÷ 历史正向采购入库量；采购退货数据尚不完整。"}{" "}
            上市时间取商品档案，平台上架时间尚未接入。
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
              disabled={saving}
              onClick={onClose}
            >
              取消
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "保存中…" : "保存规则"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
