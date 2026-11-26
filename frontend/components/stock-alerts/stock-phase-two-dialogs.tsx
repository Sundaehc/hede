"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  getStockArrivalBoard,
  getStockClearanceWeek,
  listStockCampaigns,
  saveStockCampaign,
  saveStockClearanceRecovery,
} from "@/lib/api"
import type {
  ArrivalBoard,
  ArrivalScope,
  Campaign,
  ClearanceRecovery,
  ClearanceWeek,
} from "@/lib/stock-planning"

const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 })
const fmt = (value: number | string | null) => {
  if (value == null) return "—"
  if (typeof value === "number") return number.format(value)
  const [whole, fraction] = value.split(".")
  return number.format(BigInt(whole)) + (fraction ? `.${fraction}` : "")
}
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "操作未完成，请重试。"
const small = "text-xs leading-relaxed text-muted-foreground"
const table =
  "w-full min-w-max text-left text-sm tabular-nums [&_td]:border-t [&_td]:px-3 [&_td]:py-2 [&_th]:bg-muted/70 [&_th]:px-3 [&_th]:py-2 [&_th]:text-xs [&_th]:font-medium"

const arrivalScopes: Record<ArrivalScope, string> = {
  confirmed: "未来两天确认到仓",
  due_soon: "约定临期",
  overdue: "约定超期",
}

export function StockArrivalsDialog({
  brand,
  onClose,
  openProduct,
}: {
  brand: string
  onClose: () => void
  openProduct: (id: number) => void
}) {
  const [scope, setScope] = useState<ArrivalScope>("confirmed")
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{
    key: string
    data: ArrivalBoard | null
    error: string
  }>({ key: "", data: null, error: "" })
  const key = `${brand}/${scope}/${page}/${revision}`
  useEffect(() => {
    const controller = new AbortController()
    getStockArrivalBoard(brand, scope, page, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ key, data, error: "" })
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ key, data: null, error: errorText(error) })
      })
    return () => controller.abort()
  }, [brand, scope, page, key])
  const current = state.key === key ? state : null
  const data = current?.data
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-5xl">
        <DialogTitle>到货清单</DialogTitle>
        <DialogDescription>
          按当前品牌查看首单与补单的采购交期和确认到仓情况。
        </DialogDescription>
        <div
          className="mt-3 flex flex-wrap gap-2"
          role="group"
          aria-label="到货状态"
        >
          {(Object.keys(arrivalScopes) as ArrivalScope[]).map((value) => (
            <Button
              key={value}
              size="sm"
              variant={scope === value ? "default" : "outline"}
              aria-pressed={scope === value}
              onClick={() => {
                setScope(value)
                setPage(1)
              }}
            >
              {arrivalScopes[value]}
            </Button>
          ))}
        </div>
        <div className="mt-3 min-h-64" aria-busy={!current}>
          {!current && (
            <p className={small} role="status">
              正在读取到货清单…
            </p>
          )}
          {current?.error && (
            <div className="space-y-2">
              <p className="text-sm text-destructive" role="alert">
                {current.error}
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setRevision((value) => value + 1)}
              >
                重试
              </Button>
            </div>
          )}
          {data && (
            <>
              <p className={small}>
                {scope === "confirmed"
                  ? `${data.today} 至 ${data.through} · `
                  : ""}
                共 {data.total} 笔款色采购记录
              </p>
              {data.items.length ? (
                <div className="mt-2 overflow-auto rounded-lg border">
                  <table className={table}>
                    <thead>
                      <tr>
                        <th>货号</th>
                        <th>采购单</th>
                        <th>供应商</th>
                        <th>约定日</th>
                        <th>未收（双）</th>
                        <th>确认到仓</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((order) => (
                        <tr key={`${order.id}/${order.product_id}`}>
                          <td>
                            <button
                              type="button"
                              className="font-mono text-primary underline-offset-4 hover:underline"
                              onClick={() => openProduct(order.product_id)}
                            >
                              {order.sku}
                            </button>
                          </td>
                          <td>
                            <Link
                              className="text-primary underline-offset-4 hover:underline"
                              href={`/purchase-orders/${order.id}`}
                            >
                              {order.number ?? `#${order.id}`}
                            </Link>
                            <div className={small}>{order.kind}</div>
                          </td>
                          <td>{order.supplier || "—"}</td>
                          <td>{order.due ?? "—"}</td>
                          <td>{fmt(order.remaining)}</td>
                          <td>
                            {order.confirmation?.credible ? (
                              <>
                                {order.confirmation.eta}
                                <div className={small}>
                                  {fmt(
                                    Object.values(
                                      order.confirmation.sizes
                                    ).reduce((sum, value) => sum + value, 0)
                                  )}{" "}
                                  双
                                </div>
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p
                  className={`mt-3 rounded-lg border border-dashed p-4 ${small}`}
                >
                  {data.source_ready
                    ? "暂无符合条件的到货记录。"
                    : "采购或入库数据源待核对。"}
                </p>
              )}
              {data.total > data.page_size && (
                <div className="mt-3 flex items-center justify-end gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={data.page <= 1}
                    onClick={() => setPage(data.page - 1)}
                  >
                    上一页
                  </Button>
                  <span className={small}>第 {data.page} 页</span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={data.page * data.page_size >= data.total}
                    onClick={() => setPage(data.page + 1)}
                  >
                    下一页
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function StockCampaignDialog({
  brand,
  canEdit,
  onClose,
}: {
  brand: string
  canEdit: boolean
  onClose: () => void
}) {
  const [items, setItems] = useState<Campaign[] | null>(null)
  const [name, setName] = useState("")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [factor, setFactor] = useState("1")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    listStockCampaigns(brand, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setItems(result.items)
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error))
      })
    return () => controller.abort()
  }, [brand])
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogTitle>营销日历</DialogTitle>
        <DialogDescription>
          按当前品牌录入重点活动。系数仅作用于需求窗口内与活动重叠的日期，已保存活动可回看。
        </DialogDescription>
        {canEdit && (
          <form
            className="mt-4 grid grid-cols-2 gap-2 rounded-xl border bg-muted/25 p-3 sm:grid-cols-4"
            onSubmit={async (event) => {
              event.preventDefault()
              if (saving) return
              setError("")
              setNotice("")
              setSaving(true)
              try {
                const response = await saveStockCampaign(brand, {
                  name,
                  start_date: start,
                  end_date: end,
                  factor,
                })
                setItems((previous) => [response.item, ...(previous ?? [])])
                setNotice(response.message)
                setName("")
                setStart("")
                setEnd("")
                setFactor("1")
              } catch (error) {
                setError(errorText(error))
              } finally {
                setSaving(false)
              }
            }}
          >
            <label className="col-span-2 text-xs sm:col-span-1">
              活动名称
              <Input
                className="mt-1"
                required
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="text-xs">
              开始日期
              <Input
                className="mt-1"
                required
                type="date"
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            </label>
            <label className="text-xs">
              结束日期
              <Input
                className="mt-1"
                required
                type="date"
                min={start}
                value={end}
                onChange={(event) => setEnd(event.target.value)}
              />
            </label>
            <label className="text-xs">
              需求系数
              <Input
                className="mt-1"
                required
                type="number"
                step="0.001"
                min="0.1"
                max="10"
                value={factor}
                onChange={(event) => setFactor(event.target.value)}
              />
            </label>
            <Button
              type="submit"
              size="sm"
              disabled={saving || !name.trim()}
              className="col-span-2 w-fit sm:col-span-4"
            >
              保存活动
            </Button>
          </form>
        )}
        {error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="mt-2 text-sm text-muted-foreground">
            {notice}
          </p>
        )}
        <div className="mt-3 overflow-auto rounded-lg border">
          <table className={table}>
            <thead>
              <tr>
                <th>活动</th>
                <th>日期</th>
                <th>系数</th>
              </tr>
            </thead>
            <tbody>
              {items?.length ? (
                items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>
                      {item.start_date} 至 {item.end_date}
                    </td>
                    <td>{item.factor} 倍</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3} className={small}>
                    {items ? "暂无营销活动。" : "正在读取营销日历…"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={saving}
          >
            关闭
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RecoveryEditor({
  initial,
  save,
  onClose,
}: {
  initial: ClearanceRecovery | null
  save: (values: ClearanceRecovery) => Promise<void>
  onClose: () => void
}) {
  const [amount, setAmount] = useState(
    initial?.amount == null ? "" : String(initial.amount)
  )
  const [reference, setReference] = useState(initial?.reference ?? "")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const valid = /^\d{1,14}(\.\d{1,2})?$/.test(amount) && !!reference.trim()
  return (
    <form
      className="flex flex-wrap items-end gap-2 bg-muted/35 p-3"
      onSubmit={async (event) => {
        event.preventDefault()
        if (!valid || pending) return
        setPending(true)
        setError("")
        try {
          await save({ amount, reference: reference.trim() })
          onClose()
        } catch (error) {
          setError(errorText(error))
        } finally {
          setPending(false)
        }
      }}
    >
      <label className="text-xs">
        确认回收金额（元）
        <Input
          className="mt-1 w-36"
          inputMode="decimal"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          required
        />
      </label>
      <label className="min-w-40 flex-1 text-xs">
        结算凭证或备注
        <Input
          className="mt-1"
          maxLength={1000}
          value={reference}
          onChange={(event) => setReference(event.target.value)}
          required
        />
      </label>
      <Button type="submit" size="sm" disabled={!valid || pending}>
        确认金额
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled={pending}
        onClick={onClose}
      >
        取消
      </Button>
      {error && (
        <p role="alert" className="basis-full text-sm text-destructive">
          {error}
        </p>
      )}
    </form>
  )
}

export function StockClearanceWeekDialog({
  brand,
  first,
  onClose,
  onSaved,
}: {
  brand: string
  first: string
  onClose: () => void
  onSaved: () => void
}) {
  const [data, setData] = useState<ClearanceWeek | null>(null)
  const [error, setError] = useState("")
  const [editing, setEditing] = useState<number | null>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getStockClearanceWeek(brand, first, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result)
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error))
      })
    return () => controller.abort()
  }, [brand, first, revision])
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-4xl">
        <DialogTitle>清货周复盘</DialogTitle>
        <DialogDescription>
          {first}
          {data && ` 至 ${data.end}`} · 统计本周完成清货待办的款色。
        </DialogDescription>
        {error && (
          <div className="mt-3 flex items-center gap-2">
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setError("")
                setRevision((value) => value + 1)
              }}
            >
              重试
            </Button>
          </div>
        )}
        {!data && !error && (
          <p className="mt-3 text-sm text-muted-foreground" role="status">
            正在读取清货复盘…
          </p>
        )}
        {data && (
          <>
            <div className="my-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="rounded-lg bg-muted/60 p-2.5 text-sm">
                清货款色 <strong>{data.clearance_products}</strong>
              </div>
              <div className="rounded-lg bg-muted/60 p-2.5 text-sm">
                周末库存有记录 <strong>{data.stock_covered}</strong>
              </div>
              <div className="rounded-lg bg-muted/60 p-2.5 text-sm">
                已确认回收 <strong>{fmt(data.recovery_amount)}</strong> 元{" "}
                <span className={small}>· {data.recovery_covered} 款</span>
              </div>
            </div>
            {!data.items.length ? (
              <p className={small}>没有可核对的清货款明细。</p>
            ) : (
              <div className="overflow-auto rounded-lg border">
                <table className={table}>
                  <thead>
                    <tr>
                      <th>货号</th>
                      <th>清仓净销（双）</th>
                      <th>周末尺码库存（双）</th>
                      <th>回收金额（元）</th>
                      {data.can_confirm && <th>财务确认</th>}
                    </tr>
                  </thead>
                  {data.items.map((item) => (
                    <tbody key={item.product_id}>
                      <tr>
                        <td className="font-mono">{item.sku}</td>
                        <td>{fmt(item.net_sales)}</td>
                        <td>{fmt(item.ending_stock)}</td>
                        <td>
                          {fmt(item.recovery?.amount ?? null)}
                          {item.recovery && (
                            <div className="max-w-48 text-xs break-words whitespace-normal text-muted-foreground">
                              {item.recovery.reference}
                            </div>
                          )}
                        </td>
                        {data.can_confirm && (
                          <td>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setEditing(item.product_id)}
                            >
                              {item.recovery ? "更新金额" : "录入金额"}
                            </Button>
                          </td>
                        )}
                      </tr>
                      {editing === item.product_id && (
                        <tr>
                          <td colSpan={5}>
                            <RecoveryEditor
                              initial={item.recovery}
                              onClose={() => setEditing(null)}
                              save={async (values) => {
                                await saveStockClearanceRecovery(
                                  brand,
                                  first,
                                  item.product_id,
                                  values
                                )
                                setError("")
                                onSaved()
                                setRevision((value) => value + 1)
                              }}
                            />
                          </td>
                        </tr>
                      )}
                    </tbody>
                  ))}
                </table>
              </div>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              周末库存取尺码历史快照，缺记录显示「—」。金额以财务凭证为准，不从平台销售额推算。
            </p>
          </>
        )}
        <div className="mt-4 flex justify-end">
          <Button variant="outline" size="sm" onClick={onClose}>
            关闭
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
