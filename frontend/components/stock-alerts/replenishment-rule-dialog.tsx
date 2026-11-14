"use client"

import { useEffect, useState } from "react"
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
import { getReplenishmentRule, saveReplenishmentRule } from "@/lib/api"
import type { ReplenishmentRuleResponse } from "@/lib/stock-replenishment"

export function ReplenishmentRuleDialog({
  brand,
  brandLabel,
  supplier,
  onClose,
  onSaved,
}: {
  brand: string
  brandLabel: string
  supplier: string
  onClose: () => void
  onSaved: () => void
}) {
  const [result, setResult] = useState<ReplenishmentRuleResponse | null>(null)
  const [lead, setLead] = useState("")
  const [minimum, setMinimum] = useState("")
  const [cover, setCover] = useState("14")
  const [ratios, setRatios] = useState<Record<string, Record<string, string>>>(
    {}
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getReplenishmentRule(brand, supplier, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return
        setResult(response)
        setLead(response.rule ? String(response.rule.lead_days) : "")
        setMinimum(response.rule ? String(response.rule.min_order_qty) : "")
        setCover(String(response.rule?.cover_days ?? 14))
        setRatios(
          Object.fromEntries(
            Object.entries(response.groups).map(([group, sizes]) => [
              group,
              Object.fromEntries(
                sizes.map(({ name }) => [
                  name,
                  String(response.rule?.size_ratios[group]?.[name] ?? ""),
                ])
              ),
            ])
          )
        )
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error ? cause.message : "规则读取失败，请重试"
          )
      })
    return () => controller.abort()
  }, [brand, supplier, retry])

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>供应商补货规则</DialogTitle>
          <DialogDescription>
            {brandLabel} · {supplier}。保存后对所有有查看权限的账户生效。
          </DialogDescription>
        </DialogHeader>
        <form
          className="mt-5 space-y-5"
          onSubmit={async (event) => {
            event.preventDefault()
            if (saving || !result) return
            const values: Record<string, Record<string, number>> = {}
            for (const [group, sizes] of Object.entries(ratios)) {
              if (!Object.values(sizes).some((value) => value !== "")) continue
              const weights = Object.fromEntries(
                Object.entries(sizes).map(([name, value]) => [
                  name,
                  Number(value || 0),
                ])
              )
              if (!Object.values(weights).some((value) => value > 0)) {
                setError(`尺码组“${group}”至少填写一个大于 0 的配比`)
                return
              }
              values[group] = weights
            }
            setSaving(true)
            setError(null)
            try {
              await saveReplenishmentRule({
                brand,
                supplier,
                lead_days: Number(lead),
                min_order_qty: Number(minimum),
                cover_days: Number(cover),
                size_ratios: values,
                version: result.rule?.version ?? 0,
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
          {!result && (
            <p role="status" className="text-sm text-muted-foreground">
              {error ? "规则尚未加载" : "正在读取供应商规则…"}
            </p>
          )}
          {result && (
            <>
              <div className="rounded-lg border bg-muted/30 p-3 text-sm leading-6">
                起订量按当前品牌下该供应商的所有商品合计；未达起订量只提示差额，不自动增加商品数量。
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <label className="space-y-2 text-sm">
                  <span>供应商交期（天）</span>
                  <Input
                    aria-label="供应商交期"
                    type="number"
                    min={0}
                    max={365}
                    step={1}
                    required
                    value={lead}
                    disabled={saving}
                    onChange={(event) => setLead(event.target.value)}
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span>供应商合计起订量（双）</span>
                  <Input
                    aria-label="供应商合计起订量"
                    type="number"
                    min={1}
                    max={1000000}
                    step={1}
                    required
                    value={minimum}
                    disabled={saving}
                    onChange={(event) => setMinimum(event.target.value)}
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span>到货后备货（天）</span>
                  <Input
                    aria-label="到货后备货天数"
                    type="number"
                    min={1}
                    max={365}
                    step={1}
                    required
                    value={cover}
                    disabled={saving}
                    onChange={(event) => setCover(event.target.value)}
                  />
                </label>
              </div>
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-semibold">尺码需求配比</h3>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    例如 1 : 2 : 3 : 2。填 0 表示不分配需求，留空的尺码按 0
                    保存；整个尺码组未填写时暂不生成分码建议。配比用于估算需求，不强制按整包下单。
                  </p>
                </div>
                {Object.entries(result.groups).map(([group, sizes]) => (
                  <fieldset
                    key={group}
                    disabled={saving}
                    className="rounded-lg border p-3"
                  >
                    <legend className="px-1 text-sm font-medium">
                      {group || "未关联尺码组"}
                    </legend>
                    {sizes.length ? (
                      <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
                        {sizes.map(({ name }) => (
                          <label key={name} className="space-y-1.5 text-xs">
                            <span>{name}</span>
                            <Input
                              aria-label={`${group} ${name} 配比`}
                              type="number"
                              min={0}
                              max={10000}
                              step={1}
                              placeholder="0"
                              value={ratios[group]?.[name] ?? ""}
                              onChange={(event) =>
                                setRatios((current) => ({
                                  ...current,
                                  [group]: {
                                    ...current[group],
                                    [name]: event.target.value,
                                  },
                                }))
                              }
                            />
                          </label>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-amber-700 dark:text-amber-300">
                        请先在商品档案和尺码组管理中完善尺码。
                      </p>
                    )}
                  </fieldset>
                ))}
              </div>
            </>
          )}
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
            {!result && error ? (
              <Button
                type="button"
                onClick={() => {
                  setError(null)
                  setRetry((value) => value + 1)
                }}
              >
                重新加载
              </Button>
            ) : (
              <Button type="submit" disabled={!result || saving}>
                {saving ? "保存中…" : "保存规则"}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
