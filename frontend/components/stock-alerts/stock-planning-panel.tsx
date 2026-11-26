"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import {
  getStockPlan,
  saveStockArrival,
  saveStockPurchaseOrderLink,
  saveStockSizeBaseline,
} from "@/lib/api"
import type {
  ArrivalWrite,
  Campaign,
  OrderLinkWrite,
  PlanFilters,
  PlanningOrder,
  Quantities,
  StockPlan,
} from "@/lib/stock-planning"
import { cn } from "@/lib/utils"

const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 })
const qty = (value: number | null | undefined) =>
  value == null ? "—" : number.format(value)
const getError = (error: unknown) =>
  error instanceof Error ? error.message : "操作未完成，请重试。"
const card = "min-w-0 rounded-xl border border-border bg-card p-4"
const muted = "text-xs leading-relaxed text-muted-foreground"
const table =
  "w-full text-left text-xs [&_td]:p-2 [&_th]:p-2 [&_th]:bg-muted/60 [&_th]:font-medium [&_td]:border-t [&_td]:border-border"
const positiveInt = (value: string) =>
  /^\d+$/.test(value) && Number(value) > 0 && Number(value) <= 1_000_000
const readySize = (value: string) =>
  /^\d{1,7}$/.test(value) && Number(value) <= 1_000_000
const orderStatus = {
  received: "已收齐",
  unknown: "待核对",
  overdue: "超期未收",
  due_soon: "约定临期",
  scheduled: "待到货",
}
const basisText = {
  same_product: "当前款色近 30 天分码净销",
  category: "同品类配比",
  other_color: "同原始货号其他颜色近 30 天分码净销",
  related_category: "选定近品类配比",
  manual: "有效样本不足，请手动配码",
}

function CampaignOption({ campaign }: { campaign: Campaign }) {
  return (
    <option value={campaign.id}>
      {campaign.name} · {campaign.factor} 倍
    </option>
  )
}

function QuantityInputs({
  sizes,
  values,
  label,
  max,
  onChange,
}: {
  sizes: string[]
  values: Record<string, string>
  label: string
  max?: Quantities
  onChange: (size: string, value: string) => void
}) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
      {sizes.map((size) => (
        <label key={size} className={muted}>
          {size} 码{max && <span> · 上限 {max[size]}</span>}
          <Input
            className="mt-1 tabular-nums"
            aria-label={`${label} ${size} 码`}
            type="number"
            inputMode="numeric"
            min="0"
            step="1"
            max={max?.[size] ?? 1_000_000}
            value={values[size] ?? "0"}
            onChange={(event) => onChange(size, event.target.value)}
          />
        </label>
      ))}
    </div>
  )
}

function ArrivalEditor({
  order,
  today,
  onClose,
  save,
}: {
  order: PlanningOrder
  today: string
  onClose: () => void
  save: (values: ArrivalWrite) => Promise<void>
}) {
  const sizes = Object.keys(order.remaining_sizes).filter(
    (size) => order.remaining_sizes[size] > 0
  )
  const [eta, setEta] = useState(order.confirmation?.eta ?? "")
  const [note, setNote] = useState("")
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      sizes.map((size) => [size, String(order.confirmation?.sizes[size] ?? 0)])
    )
  )
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const quantityOk =
    sizes.every(
      (size) =>
        readySize(values[size]) &&
        Number(values[size]) <= order.remaining_sizes[size]
    ) && sizes.some((size) => Number(values[size]) > 0)
  const submit = async (remove: boolean) => {
    if (pending || !note.trim() || (!remove && (!quantityOk || eta < today)))
      return
    setPending(true)
    setError("")
    try {
      await save({
        order_id: order.id,
        eta: remove ? null : eta,
        sizes: remove
          ? {}
          : Object.fromEntries(
              sizes.map((size) => [size, Number(values[size])])
            ),
        note: note.trim(),
      })
      onClose()
    } catch (error) {
      setError(getError(error))
    } finally {
      setPending(false)
    }
  }
  return (
    <form
      className="mt-3 space-y-3 rounded-lg border bg-muted/25 p-3"
      onSubmit={(event) => {
        event.preventDefault()
        void submit(false)
      }}
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className={muted}>
          预计到仓日
          <Input
            className="mt-1"
            type="date"
            min={today}
            value={eta}
            onChange={(event) => setEta(event.target.value)}
          />
        </label>
        <label className={cn(muted, "min-w-40 flex-1")}>
          确认依据
          <Input
            className="mt-1"
            maxLength={1000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="如工厂确认时间或发货单号"
          />
        </label>
      </div>
      {sizes.length > 0 && (
        <QuantityInputs
          sizes={sizes}
          values={values}
          label="到仓数量"
          max={order.remaining_sizes}
          onChange={(size, value) =>
            setValues((previous) => ({ ...previous, [size]: value }))
          }
        />
      )}
      <p className={muted}>填写确认可到仓的未收双数。撤销也需填写依据。</p>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={
            pending || !quantityOk || !eta || eta < today || !note.trim()
          }
        >
          保存到仓确认
        </Button>
        {order.confirmation?.eta && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pending || !note.trim()}
            onClick={() => void submit(true)}
          >
            撤销确认
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={pending}
          onClick={onClose}
        >
          取消
        </Button>
      </div>
    </form>
  )
}

function OrderLinkEditor({
  order,
  close,
  save,
}: {
  order: PlanningOrder
  close: () => void
  save: (values: OrderLinkWrite) => Promise<void>
}) {
  const [external, setExternal] = useState(order.external_number ?? "")
  const [note, setNote] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  return (
    <form
      className="mt-2 space-y-2 rounded-lg border bg-muted/25 p-3"
      onSubmit={async (event) => {
        event.preventDefault()
        if (saving || !external.trim() || !note.trim()) return
        setSaving(true)
        setError("")
        try {
          await save({
            order_id: order.id,
            external_number: external.trim(),
            note: note.trim(),
          })
          close()
        } catch (error) {
          setError(getError(error))
        } finally {
          setSaving(false)
        }
      }}
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className={muted}>
          聚水潭采购单号
          <Input
            className="mt-1"
            value={external}
            maxLength={100}
            required
            onChange={(event) => setExternal(event.target.value)}
          />
        </label>
        <label className={cn(muted, "min-w-40 flex-1")}>
          核对依据
          <Input
            className="mt-1"
            value={note}
            maxLength={1000}
            required
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
      </div>
      <p className={muted}>
        按同一采购单核对两个系统的单号。变更关联将撤销该采购单已有的到仓确认。
      </p>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={saving || !external.trim() || !note.trim()}
        >
          保存采购单号关联
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={saving}
          onClick={close}
        >
          取消
        </Button>
      </div>
    </form>
  )
}

function Arrivals({
  plan,
  canConfirm,
  save,
  saveLink,
}: {
  plan: StockPlan
  canConfirm: boolean
  save: (values: ArrivalWrite) => Promise<void>
  saveLink: (values: OrderLinkWrite) => Promise<void>
}) {
  const [editing, setEditing] = useState<{
    id: number
    mode: "arrival" | "link"
  } | null>(null)
  return (
    <section className={card} aria-label="采购交期与到货">
      <h3 className="mb-2 text-sm font-semibold">采购交期与到货</h3>
      <p className={muted}>
        首单／补单按已关联采购记录判断；约定交期和确认到仓日分别展示。
      </p>
      {!plan.orders?.length ? (
        <p className={cn(muted, "mt-3")}>
          {plan.orders
            ? "未查到已关联的采购订单。"
            : "无采购查看权限或采购来源待核对。"}
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {plan.orders.map((order) => (
            <li key={order.id} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Link
                    href={`/purchase-orders/${order.id}`}
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {order.number || `#${order.id}`}
                  </Link>
                  <span className="rounded bg-muted px-1.5 py-0.5">
                    {order.kind}
                  </span>
                  <span
                    className={cn(
                      order.status === "overdue"
                        ? "text-destructive"
                        : "text-muted-foreground"
                    )}
                  >
                    {orderStatus[order.status]}
                  </span>
                </div>
                {canConfirm && editing?.id !== order.id && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEditing({ id: order.id, mode: "link" })}
                    >
                      {order.external_number
                        ? "修改关联单号"
                        : "关联聚水潭单号"}
                    </Button>
                    {(Object.values(order.remaining_sizes).some(
                      (quantity) => quantity > 0
                    ) ||
                      order.confirmation?.eta) && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setEditing({ id: order.id, mode: "arrival" })
                        }
                      >
                        {order.confirmation?.eta ? "更新到仓确认" : "确认到仓"}
                      </Button>
                    )}
                  </div>
                )}
              </div>
              <p className={cn(muted, "mt-1 tabular-nums")}>
                {order.supplier && `${order.supplier} · `}约定{" "}
                {order.due ?? "—"} · 订货 {qty(order.ordered)} · 已收{" "}
                {qty(order.received)} · 未收 {qty(order.remaining)} 双
              </p>
              <p className={muted}>
                {order.external_number
                  ? `聚水潭单号 ${order.external_number}`
                  : "未录入聚水潭单号"}
                {!order.receipts_verified && " · 实收待核对"}
              </p>
              {order.confirmation?.eta && (
                <p className={muted}>
                  确认到仓 {order.confirmation.eta} · 剩余确认{" "}
                  {qty(
                    Object.values(order.confirmation.sizes).reduce(
                      (sum, value) => sum + value,
                      0
                    )
                  )}{" "}
                  双{!order.confirmation.credible ? " · 已失效或需核对" : ""}
                  {order.confirmation.note && ` · ${order.confirmation.note}`}
                </p>
              )}
              {editing?.id === order.id && editing.mode === "link" && (
                <OrderLinkEditor
                  key={order.id}
                  order={order}
                  save={saveLink}
                  close={() => setEditing(null)}
                />
              )}
              {editing?.id === order.id && editing.mode === "arrival" && (
                <ArrivalEditor
                  key={order.id}
                  order={order}
                  today={plan.today}
                  save={save}
                  onClose={() => setEditing(null)}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function StockPlanningPanel({
  brand,
  productId,
  manager,
}: {
  brand: string
  productId: number
  manager: boolean
}) {
  const { hasPermission } = useAuth()
  const [plan, setPlan] = useState<StockPlan | null>(null)
  const [filters, setFilters] = useState<PlanFilters>({})
  const [revision, setRevision] = useState(0)
  const [need, setNeed] = useState("")
  const [total, setTotal] = useState("")
  const [campaign, setCampaign] = useState("")
  const [reference, setReference] = useState("")
  const [adjust, setAdjust] = useState<Record<string, string> | null>(null)
  const [copied, setCopied] = useState(false)
  const [baseline, setBaseline] = useState<Record<string, string> | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [loading, setLoading] = useState(true)

  const reload = () => {
    setLoading(true)
    setError("")
    setRevision((value) => value + 1)
  }
  useEffect(() => {
    const controller = new AbortController()
    getStockPlan(brand, productId, filters, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setPlan(result)
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(getError(error))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [brand, productId, filters, revision])

  if (!plan)
    return (
      <div className={card}>
        {error ? (
          <>
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
            <Button variant="outline" size="sm" onClick={reload}>
              重试
            </Button>
          </>
        ) : (
          <p role="status" className={muted}>
            正在读取补单与到货…
          </p>
        )}
      </div>
    )

  const totalSent = plan.total
  const adjusted = Object.fromEntries(
    plan.sizes.map((size) => [
      size,
      adjust?.[size] ?? String(plan.suggested?.[size] ?? 0),
    ])
  )
  const adjustedTotal = Object.values(adjusted).reduce(
    (sum, value) => sum + Number(value || 0),
    0
  )
  const balance =
    totalSent != null &&
    adjustedTotal === totalSent &&
    Object.values(adjusted).every(readySize)
  const destination = need || plan.need_by
  const eligible = Object.values(plan.eligible_transit).reduce(
    (sum, value) => sum + value,
    0
  )
  const canUseBaseline =
    manager && plan.category && plan.category !== "0" && plan.sizes.length > 0
  const changeSeason = (season: string) => {
    setReference("")
    setBaseline(null)
    setAdjust(null)
    setCopied(false)
    setLoading(true)
    setError("")
    setNotice("")
    setFilters((previous) => ({
      total: previous.total,
      need_by: previous.need_by,
      campaign_id: previous.campaign_id,
      season,
    }))
  }
  const referenceLabel =
    plan.reference &&
    [plan.reference.label, plan.reference.color].filter(Boolean).join(" · ")
  return (
    <div className="space-y-3">
      <section className={card} aria-label="补单配码与需求试算">
        <div className="flex flex-wrap items-baseline justify-between gap-1.5">
          <h3 className="text-sm font-semibold">补单配码与需求试算</h3>
          <span className={muted}>
            {[
              plan.sku,
              plan.color,
              plan.category,
              plan.heel_group || "跟高未登记",
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (loading || (total && !positiveInt(total))) return
            setLoading(true)
            setError("")
            setNotice("")
            setCopied(false)
            setAdjust(null)
            setFilters({
              need_by: destination,
              total: total ? Number(total) : undefined,
              campaign_id: campaign ? Number(campaign) : undefined,
              season: plan.allocation_season,
              reference_product_id: reference.startsWith("color:")
                ? Number(reference.slice(6))
                : undefined,
              reference_category: reference.startsWith("category:")
                ? reference.slice(9)
                : undefined,
            })
          }}
        >
          <label className={muted}>
            补单总量（双）
            <Input
              className="mt-1 w-32"
              type="number"
              min="1"
              max="1000000"
              step="1"
              value={total}
              onChange={(event) => setTotal(event.target.value)}
            />
          </label>
          <label className={muted}>
            需求日期
            <Input
              className="mt-1"
              type="date"
              min={plan.today}
              value={destination}
              onChange={(event) => setNeed(event.target.value)}
            />
          </label>
          <label className={cn(muted, "min-w-36 flex-1")}>
            营销活动
            <Select
              className="mt-1"
              value={campaign}
              onChange={(event) => setCampaign(event.target.value)}
            >
              <option value="">仅日常需求</option>
              {plan.campaigns.map((entry) => (
                <CampaignOption key={entry.id} campaign={entry} />
              ))}
            </Select>
          </label>
          <Button
            type="submit"
            size="lg"
            disabled={loading || (!!total && !positiveInt(total))}
          >
            {loading ? "正在试算…" : total ? "生成配码" : "试算需求"}
          </Button>
          <div className="grid basis-full gap-2 border-t border-border pt-2 sm:grid-cols-2">
            <label className={muted}>
              销售季节
              <Select
                className="mt-1"
                value={filters.season ?? plan.allocation_season}
                disabled={loading || plan.allocation_seasons.length < 2}
                onChange={(event) => changeSeason(event.target.value)}
              >
                {plan.allocation_seasons.map((season) => (
                  <option key={season} value={season}>
                    {season || "档案未登记"}
                  </option>
                ))}
              </Select>
            </label>
            <label className={muted}>
              配码参考
              <Select
                className="mt-1"
                value={reference}
                disabled={loading}
                onChange={(event) => setReference(event.target.value)}
              >
                <option value="">当前款色销量 / 同品类配比</option>
                {plan.baseline && (
                  <option value={`category:${plan.category}`}>
                    指定同品类配比
                  </option>
                )}
                {plan.other_colors.length > 0 && (
                  <optgroup label="同原始货号其他颜色">
                    {plan.other_colors.map((item) => (
                      <option key={item.id} value={`color:${item.id}`}>
                        {item.color} · {item.sku}
                      </option>
                    ))}
                  </optgroup>
                )}
                {plan.related_categories.length > 0 && (
                  <optgroup label="同季节、跟高及尺码组的近品类">
                    {plan.related_categories.map((item) => (
                      <option key={item} value={`category:${item}`}>
                        {item}
                      </option>
                    ))}
                  </optgroup>
                )}
              </Select>
            </label>
          </div>
        </form>
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
        {plan.blocked_reason && (
          <p className="mt-3 text-sm text-destructive">
            {plan.blocked_reason}，已停止生成补单配码。
          </p>
        )}
        <div
          aria-busy={loading}
          className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3"
        >
          <div className="rounded-lg bg-muted/60 p-2.5">
            日常需求{" "}
            <strong className="tabular-nums">{qty(plan.demand.normal)}</strong>
            <p className={muted}>缺口 {qty(plan.demand.normal_shortage)} 双</p>
          </div>
          <div className="rounded-lg bg-muted/60 p-2.5">
            活动需求{" "}
            <strong className="tabular-nums">
              {qty(plan.demand.campaign)}
            </strong>
            <p className={muted}>
              缺口 {qty(plan.demand.campaign_shortage)} 双
            </p>
          </div>
          <div className="col-span-2 rounded-lg bg-muted/60 p-2.5 sm:col-span-1">
            可抵扣在途{" "}
            <strong className="tabular-nums">
              {plan.stock_ready ? qty(eligible) : "—"}
            </strong>
            <p className={muted}>{plan.need_by} 前可到仓</p>
          </div>
        </div>
        {plan.selected_campaign && (
          <p className={cn(muted, "mt-2")}>
            {plan.selected_campaign.name} · 系数 {plan.selected_campaign.factor}{" "}
            · 本次覆盖 {plan.demand.campaign_days} 个活动日
          </p>
        )}
        <p className={cn(muted, "mt-2")}>
          库存 {plan.stock_date ?? "未知"} ·{" "}
          {plan.sales_start && plan.cutoff
            ? `销售统计 ${plan.sales_start} 至 ${plan.cutoff}`
            : plan.cutoff
              ? `日销同步至 ${plan.cutoff}，暂无该款上市后的销售统计`
              : "近 30 天无可对齐的日销数据"}
          {plan.sales_start &&
            (plan.sales_complete
              ? "（非清仓净销）"
              : "（数据缺日，暂停自动配码）")}
          {!plan.stock_ready &&
            " · 库存未对齐、缺失或分码有冲突，暂不自动配码及抵扣。"}
        </p>
        {totalSent != null && plan.sizes.length > 0 && !plan.blocked_reason && (
          <div className="mt-4 space-y-2 border-t pt-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h4 className="text-sm font-medium">配码试算结果</h4>
              <span className={muted}>
                {adjust
                  ? "手动配码"
                  : plan.suggested
                    ? basisText[plan.basis]
                    : plan.reference &&
                        !Object.keys(plan.reference.weights).length
                      ? "参考款色样本不足，可改选或手调"
                      : "未生成自动建议，可手动填写"}
              </span>
            </div>
            <p className={muted}>
              {[
                plan.allocation_season || "季节未登记",
                plan.heel_group || "跟高未登记",
                referenceLabel,
                plan.reference?.sales_start && plan.reference.cutoff
                  ? `${plan.reference.sales_start} 至 ${plan.reference.cutoff}`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
              。补后库存为现货、可抵扣在途和本次补单之和，供核对配码。
            </p>
            <div className="overflow-auto rounded-lg border">
              <table className={cn(table, "min-w-[36rem] tabular-nums")}>
                <thead>
                  <tr>
                    <th>尺码</th>
                    <th>现货</th>
                    <th>近 30 天净销</th>
                    {plan.reference?.kind === "other_color" && (
                      <th>参考色净销</th>
                    )}
                    <th>可抵扣在途</th>
                    <th>本次补单</th>
                    <th>补后库存</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.sizes.map((size) => (
                    <tr key={size}>
                      <td>{size}</td>
                      <td>
                        {qty(plan.stock_ready ? (plan.stock[size] ?? 0) : null)}
                      </td>
                      <td>
                        {qty(
                          plan.sales_complete ? (plan.sales[size] ?? 0) : null
                        )}
                      </td>
                      {plan.reference?.kind === "other_color" && (
                        <td>
                          {qty(
                            plan.reference.sales
                              ? (plan.reference.sales[size] ?? 0)
                              : null
                          )}
                        </td>
                      )}
                      <td>
                        {qty(
                          plan.stock_ready
                            ? (plan.eligible_transit[size] ?? 0)
                            : null
                        )}
                      </td>
                      <td>
                        <Input
                          className="h-8 w-20"
                          aria-label={`补单 ${size} 码`}
                          type="number"
                          min="0"
                          max="1000000"
                          step="1"
                          value={adjusted[size]}
                          disabled={loading}
                          onChange={(event) => {
                            setCopied(false)
                            setAdjust({
                              ...adjusted,
                              [size]: event.target.value,
                            })
                          }}
                        />
                      </td>
                      <td className="font-semibold text-primary">
                        {qty(
                          plan.stock_ready && readySize(adjusted[size])
                            ? (plan.stock[size] ?? 0) +
                                (plan.eligible_transit[size] ?? 0) +
                                Number(adjusted[size])
                            : null
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p
                className={cn(
                  "text-sm tabular-nums",
                  !balance && "text-destructive"
                )}
              >
                配码合计 {qty(adjustedTotal)} / {qty(totalSent)} 双
                {balance ? " · 数量一致" : " · 请调整至与总量一致"}
              </p>
              <Button
                size="sm"
                variant="outline"
                disabled={
                  loading ||
                  !balance ||
                  !plan.stock_ready ||
                  !plan.sales_complete
                }
                onClick={async () => {
                  try {
                    const rows = plan.sizes.map((size) =>
                      [plan.sku, size, adjusted[size]].join("\t")
                    )
                    await navigator.clipboard.writeText(
                      ["货号\t尺码\t补单双数", ...rows].join("\n")
                    )
                    setCopied(true)
                  } catch {
                    setError("无法复制，请检查浏览器的剪贴板权限。")
                  }
                }}
              >
                {copied ? "已复制" : "复制配码"}
              </Button>
            </div>
          </div>
        )}
        {plan.sizes.length === 0 && (
          <p className={cn(muted, "mt-2")}>
            该商品缺少有效尺码组，请先补齐商品档案。
          </p>
        )}
        {canUseBaseline && (
          <div className="mt-4 border-t pt-3">
            {!baseline ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setBaseline(
                    Object.fromEntries(
                      plan.sizes.map((size) => [
                        size,
                        String(
                          plan.baseline?.[size] ??
                            plan.legacy_baseline?.[size] ??
                            0
                        ),
                      ])
                    )
                  )
                }
              >
                维护品类配比
              </Button>
            ) : (
              <form
                className="space-y-2"
                onSubmit={async (event) => {
                  event.preventDefault()
                  setSaving(true)
                  setError("")
                  try {
                    const response = await saveStockSizeBaseline(
                      brand,
                      productId,
                      Object.fromEntries(
                        plan.sizes.map((size) => [size, Number(baseline[size])])
                      ),
                      plan.allocation_season
                    )
                    setBaseline(null)
                    setNotice(response.message)
                    reload()
                  } catch (error) {
                    setError(getError(error))
                  } finally {
                    setSaving(false)
                  }
                }}
              >
                <p className={muted}>
                  {[
                    plan.category,
                    plan.size_group,
                    plan.allocation_season || "季节未登记",
                    plan.heel_group || "跟高未登记",
                  ].join(" · ")}
                  。此配比用于同品牌、同品类、同季节、同跟高及同尺码组。
                </p>
                {!plan.baseline && plan.legacy_baseline && (
                  <p className={muted}>
                    已带入旧的通用品类配比供核对，保存后才用于当前季节和跟高。
                  </p>
                )}
                <QuantityInputs
                  sizes={plan.sizes}
                  values={baseline}
                  label="品类权重"
                  onChange={(size, value) =>
                    setBaseline((previous) => ({ ...previous, [size]: value }))
                  }
                />
                <div className="flex gap-2">
                  <Button
                    type="submit"
                    size="sm"
                    disabled={
                      saving ||
                      !Object.values(baseline).every(readySize) ||
                      !Object.values(baseline).some(
                        (value) => Number(value) > 0
                      )
                    }
                  >
                    保存配比
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={saving}
                    onClick={() => setBaseline(null)}
                  >
                    取消
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}
      </section>
      <Arrivals
        plan={plan}
        canConfirm={manager && hasPermission("purchase.manage")}
        saveLink={async (values) => {
          const response = await saveStockPurchaseOrderLink(
            brand,
            productId,
            values
          )
          setNotice(response.message)
          reload()
        }}
        save={async (values) => {
          const response = await saveStockArrival(brand, productId, values)
          setNotice(response.message)
          reload()
        }}
      />
    </div>
  )
}
