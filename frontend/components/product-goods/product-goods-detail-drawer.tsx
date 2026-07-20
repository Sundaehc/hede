"use client"

import { useEffect, useRef, useState } from "react"
import { Boxes, CalendarDays, TrendingUp, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { ProductGoodsItem, ProductGoodsResponse } from "@/lib/types"


type ProductGoodsOperationFields = Pick<ProductGoodsItem, "platform" | "category_l4" | "product_role" | "product_type" | "douyin_hot" | "clearance" | "remark">
type ProductGoodsReplenishmentFields = Pick<ProductGoodsItem, "replenishment_by_size" | "post_replenishment_by_size">
  & Pick<ProductGoodsItem["metrics"], "replenishment_total" | "post_replenishment_stock" | "post_replenishment_total" | "post_replenishment_turnover_days">

export type ProductGoodsManualFields = ProductGoodsOperationFields & ProductGoodsReplenishmentFields

type DrawerProps = {
  item: ProductGoodsItem | null
  data: Pick<ProductGoodsResponse, "annual_sales_columns" | "daily_dates" | "monthly_sales_columns" | "platform_columns" | "size_columns">
  canEdit: boolean
  onClose: () => void
  onSave: (item: ProductGoodsItem, fields: Partial<ProductGoodsManualFields>) => Promise<void>
  onPreviewImage: (item: ProductGoodsItem) => void
}

function display(value: unknown) {
  return value === null || value === undefined || value === "" ? "-" : String(value)
}

function metric(item: ProductGoodsItem, key: string) {
  return display(item.metrics?.[key])
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="space-y-2"><h3 className="text-sm font-semibold">{title}</h3>{children}</section>
}

function DetailField({ label, value }: { label: string; value: unknown }) {
  return <div className="rounded-lg border border-border bg-card px-3 py-2.5"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 break-words text-sm font-medium">{display(value)}</p></div>
}

function SummaryMetric({ icon: Icon, label, value }: { icon: typeof Boxes; label: string; value: unknown }) {
  return <div className="rounded-lg border border-border bg-background px-3 py-2.5"><div className="flex items-center gap-1.5 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</div><p className="mt-1 text-lg font-semibold tabular-nums">{display(value)}</p></div>
}

function SizeGrid({ title, values, sizes }: { title: string; values: Record<string, number>; sizes: string[] }) {
  const visibleSizes = sizes.filter((size) => values[size] !== undefined)
  return <DetailSection title={title}>{visibleSizes.length ? <div className="grid grid-cols-4 gap-2 sm:grid-cols-5">{visibleSizes.map((size) => <DetailField key={size} label={size} value={values[size]} />)}</div> : <p className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-sm text-muted-foreground">暂无尺码数据</p>}</DetailSection>
}

function manualValue(value: string | boolean | null) {
  return value === true ? "是" : value === false || value === null ? "" : value
}

function ManualFieldsForm({ item, canEdit, onSave }: { item: ProductGoodsItem; canEdit: boolean; onSave: DrawerProps["onSave"] }) {
  const [fields, setFields] = useState<ProductGoodsOperationFields>(() => ({
    platform: item.platform,
    category_l4: item.category_l4,
    product_role: item.product_role,
    product_type: item.product_type,
    douyin_hot: item.douyin_hot,
    clearance: item.clearance,
    remark: item.remark,
  }))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setFields({
      platform: item.platform,
      category_l4: item.category_l4,
      product_role: item.product_role,
      product_type: item.product_type,
      douyin_hot: item.douyin_hot,
      clearance: item.clearance,
      remark: item.remark,
    })
  }, [item])

  function update(field: keyof ProductGoodsOperationFields, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
  }

  if (!canEdit) {
    return <DetailSection title="运营字段"><div className="grid gap-2 sm:grid-cols-2"><DetailField label="商品角色" value={item.product_role} /><DetailField label="类型" value={item.product_type} /><DetailField label="抖音爆款" value={item.douyin_hot} /><DetailField label="清仓" value={item.clearance} /><DetailField label="备注" value={item.remark} /></div></DetailSection>
  }

  return <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); setSaving(true); void onSave(item, fields).finally(() => setSaving(false)) }}>
    <DetailSection title="运营字段"><div className="grid gap-4 sm:grid-cols-2">
      <label className="grid gap-1.5 text-sm font-medium">所属平台<Input value={manualValue(fields.platform)} onChange={(event) => update("platform", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">四级分类<Input value={manualValue(fields.category_l4)} onChange={(event) => update("category_l4", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">商品角色<Input value={manualValue(fields.product_role)} onChange={(event) => update("product_role", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">类型<Input value={manualValue(fields.product_type)} onChange={(event) => update("product_type", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">抖音爆款<Input value={manualValue(fields.douyin_hot)} onChange={(event) => update("douyin_hot", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">清仓<Input value={manualValue(fields.clearance)} onChange={(event) => update("clearance", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium sm:col-span-2">备注<Input value={manualValue(fields.remark)} onChange={(event) => update("remark", event.target.value)} disabled={saving} /></label>
    </div></DetailSection>
    <div className="flex justify-end border-t border-border pt-4"><Button type="submit" disabled={saving}>{saving ? "保存中..." : "保存运营字段"}</Button></div>
  </form>
}

type ReplenishmentDraft = {
  replenishment_by_size: Record<string, string>
  replenishment_total: string
  post_replenishment_by_size: Record<string, string>
  post_replenishment_stock: string
  post_replenishment_total: string
  post_replenishment_turnover_days: string
}

function textNumber(value: unknown) {
  return value === null || value === undefined ? "" : String(value)
}

function quantityDraft(values: Record<string, number>) {
  return Object.fromEntries(Object.entries(values).map(([size, quantity]) => [size, String(quantity)]))
}

function replenishmentDraft(item: ProductGoodsItem): ReplenishmentDraft {
  return {
    replenishment_by_size: quantityDraft(item.replenishment_by_size),
    replenishment_total: textNumber(item.metrics?.replenishment_total),
    post_replenishment_by_size: quantityDraft(item.post_replenishment_by_size),
    post_replenishment_stock: textNumber(item.metrics?.post_replenishment_stock),
    post_replenishment_total: textNumber(item.metrics?.post_replenishment_total),
    post_replenishment_turnover_days: textNumber(item.metrics?.post_replenishment_turnover_days),
  }
}

function numberOrNull(value: string) {
  const normalized = value.trim()
  if (!normalized) return null
  const number = Number(normalized)
  return Number.isFinite(number) && number >= 0 ? number : null
}

function quantitiesFromDraft(values: Record<string, string>, sizes: string[]) {
  return Object.fromEntries(sizes.flatMap((size) => {
    const quantity = numberOrNull(values[size] ?? "")
    return quantity === null ? [] : [[size, Math.trunc(quantity)] as [string, number]]
  }))
}

function ManualReplenishmentForm({ item, sizes, canEdit, onSave }: { item: ProductGoodsItem; sizes: string[]; canEdit: boolean; onSave: DrawerProps["onSave"] }) {
  const [fields, setFields] = useState<ReplenishmentDraft>(() => replenishmentDraft(item))
  const [saving, setSaving] = useState(false)

  useEffect(() => setFields(replenishmentDraft(item)), [item])

  function updateQuantity(field: "replenishment_by_size" | "post_replenishment_by_size", size: string, quantity: string) {
    setFields((current) => ({ ...current, [field]: { ...current[field], [size]: quantity } }))
  }

  function updateValue(field: Exclude<keyof ReplenishmentDraft, "replenishment_by_size" | "post_replenishment_by_size">, value: string) {
    setFields((current) => ({ ...current, [field]: value }))
  }

  if (!canEdit) return <DetailSection title="补单信息"><div className="grid gap-2 sm:grid-cols-2"><DetailField label="补单合计" value={metric(item, "replenishment_total")} /><DetailField label="补单后库存" value={metric(item, "post_replenishment_stock")} /><DetailField label="补单后合计" value={metric(item, "post_replenishment_total")} /><DetailField label="补单后周转天数" value={metric(item, "post_replenishment_turnover_days")} /></div></DetailSection>

  return <form className="space-y-4 border-t border-border pt-5" onSubmit={(event) => {
    event.preventDefault()
    setSaving(true)
    void onSave(item, {
      replenishment_by_size: quantitiesFromDraft(fields.replenishment_by_size, sizes),
      replenishment_total: numberOrNull(fields.replenishment_total),
      post_replenishment_by_size: quantitiesFromDraft(fields.post_replenishment_by_size, sizes),
      post_replenishment_stock: numberOrNull(fields.post_replenishment_stock),
      post_replenishment_total: numberOrNull(fields.post_replenishment_total),
      post_replenishment_turnover_days: numberOrNull(fields.post_replenishment_turnover_days),
    }).finally(() => setSaving(false))
  }}>
    <DetailSection title="补单明细"><div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{sizes.map((size) => <label key={size} className="grid gap-1 text-xs text-muted-foreground"><span>{size}</span><Input type="number" min="0" step="1" inputMode="numeric" value={fields.replenishment_by_size[size] ?? ""} onChange={(event) => updateQuantity("replenishment_by_size", size, event.target.value)} disabled={saving} /></label>)}</div></DetailSection>
    <DetailSection title="补单后尺码"><div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{sizes.map((size) => <label key={size} className="grid gap-1 text-xs text-muted-foreground"><span>{size}</span><Input type="number" min="0" step="1" inputMode="numeric" value={fields.post_replenishment_by_size[size] ?? ""} onChange={(event) => updateQuantity("post_replenishment_by_size", size, event.target.value)} disabled={saving} /></label>)}</div></DetailSection>
    <DetailSection title="补单汇总"><div className="grid gap-4 sm:grid-cols-2">
      <label className="grid gap-1.5 text-sm font-medium">补单合计<Input type="number" min="0" step="1" inputMode="numeric" value={fields.replenishment_total} onChange={(event) => updateValue("replenishment_total", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">补单后库存<Input type="number" min="0" step="1" inputMode="numeric" value={fields.post_replenishment_stock} onChange={(event) => updateValue("post_replenishment_stock", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">补单后合计<Input type="number" min="0" step="1" inputMode="numeric" value={fields.post_replenishment_total} onChange={(event) => updateValue("post_replenishment_total", event.target.value)} disabled={saving} /></label>
      <label className="grid gap-1.5 text-sm font-medium">补单后周转天数<Input type="number" min="0" step="0.1" inputMode="decimal" value={fields.post_replenishment_turnover_days} onChange={(event) => updateValue("post_replenishment_turnover_days", event.target.value)} disabled={saving} /></label>
    </div></DetailSection>
    <div className="flex justify-end"><Button type="submit" disabled={saving}>{saving ? "保存中..." : "保存补单字段"}</Button></div>
  </form>
}

export function ProductGoodsDetailDrawer({ item, data, canEdit, onClose, onSave, onPreviewImage }: DrawerProps) {
  const drawerRef = useRef<HTMLDivElement | null>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!item) return
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    drawerRef.current?.focus()
    return () => previouslyFocusedRef.current?.focus()
  }, [item])

  if (!item) return null
  const hasImage = Boolean(item.image_url)
  const annualValues = data.annual_sales_columns.filter((period) => item.annual_sales[period] !== undefined)
  const monthlyValues = data.monthly_sales_columns.filter((period) => item.monthly_sales[period] !== undefined)

  return <div ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby="product-goods-detail-title" tabIndex={-1} className="fixed inset-y-0 right-0 z-[90] w-full max-w-2xl border-l border-border bg-background/95 shadow-2xl outline-none backdrop-blur" onKeyDown={(event) => {
    if (event.key === "Escape") { event.preventDefault(); onClose(); return }
    if (event.key !== "Tab") return
    const focusable = Array.from(drawerRef.current?.querySelectorAll<HTMLElement>("button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])") ?? [])
    if (!focusable.length) return
    const first = focusable[0]; const last = focusable.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }}>
    <div className="flex h-full flex-col">
      <div className="border-b border-border bg-card/90 px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 gap-4">
            <button type="button" disabled={!hasImage} onClick={() => hasImage && onPreviewImage(item)} className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-default">{hasImage ? <img src={`/api${item.image_url}`} alt={item.goods_code || "商品图片"} className="h-full w-full object-contain" /> : <Boxes className="h-7 w-7 text-muted-foreground" />}</button>
            <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 id="product-goods-detail-title" className="truncate text-xl font-semibold">{item.goods_code || item.style_code || "未命名商品"}</h2>{item.year && <span className="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs">{item.year}</span>}</div><p className="mt-1 text-sm text-muted-foreground">款号 {display(item.style_code)} · {display(item.color)}</p><div className="mt-3 flex flex-wrap gap-1.5 text-xs text-muted-foreground"><span className="rounded-full border border-border bg-muted/40 px-2.5 py-1">{display(item.season)}</span><span className="rounded-full border border-border bg-muted/40 px-2.5 py-1">{display(item.category_l4)}</span><span className="rounded-full border border-border bg-muted/40 px-2.5 py-1">{display(item.platform)}</span></div></div>
          </div>
          <div className="flex shrink-0 gap-1"><Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭详情"><X className="h-4 w-4" /></Button></div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"><SummaryMetric icon={Boxes} label="在仓合计" value={item.stock_total} /><SummaryMetric icon={TrendingUp} label="总销量" value={metric(item, "total_sales")} /><SummaryMetric icon={TrendingUp} label="近7天销量" value={metric(item, "week_sales")} /><SummaryMetric icon={CalendarDays} label="昨日销量" value={metric(item, "yesterday_sales")} /></div>
      </div>

      <Tabs defaultValue="base" className="min-h-0 flex-1">
        <div className="sticky top-0 z-10 border-b border-border bg-background/95 px-5 py-3 backdrop-blur"><TabsList className="grid h-10 w-full grid-cols-4 rounded-xl bg-muted/50 p-1"><TabsTrigger className="rounded-lg text-xs" value="base">基础</TabsTrigger><TabsTrigger className="rounded-lg text-xs" value="operation">经营</TabsTrigger><TabsTrigger className="rounded-lg text-xs" value="sales">销售</TabsTrigger><TabsTrigger className="rounded-lg text-xs" value="stock">库存</TabsTrigger></TabsList></div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <TabsContent value="base" className="space-y-4"><DetailSection title="商品识别"><div className="grid gap-2 sm:grid-cols-2"><DetailField label="货号" value={item.goods_code} /><DetailField label="款号" value={item.style_code} /><DetailField label="年份" value={item.year} /><DetailField label="季节" value={item.season} /><DetailField label="四级分类" value={item.category_l4} /><DetailField label="颜色" value={item.color} /><DetailField label="首单日期" value={item.first_order_date} /><DetailField label="成本" value={item.cost} /></div></DetailSection><DetailSection title="工厂信息"><div className="grid gap-2 sm:grid-cols-2"><DetailField label="工厂货号" value={item.factory_sku} /><DetailField label="工厂代码" value={item.factory_code} /><DetailField label="工厂名称" value={item.factory_name} /><DetailField label="所属平台" value={item.platform} /></div></DetailSection></TabsContent>
          <TabsContent value="operation" className="space-y-4"><ManualFieldsForm item={item} canEdit={canEdit} onSave={onSave} /></TabsContent>
          <TabsContent value="sales" className="space-y-4"><div className="grid gap-3 sm:grid-cols-2"><SummaryMetric icon={TrendingUp} label="总订单量" value={metric(item, "total_order_count")} /><SummaryMetric icon={TrendingUp} label="总销量" value={metric(item, "total_sales")} /><SummaryMetric icon={CalendarDays} label="昨日销量" value={metric(item, "yesterday_sales")} /><SummaryMetric icon={TrendingUp} label="上周销量" value={metric(item, "last_week_sales")} /></div><DetailSection title="近14天每日销量"><div className="grid grid-cols-4 gap-2 sm:grid-cols-7">{data.daily_dates.map((day) => <DetailField key={day} label={day.slice(5)} value={item.daily_sales_by_date[day]} />)}</div></DetailSection><DetailSection title="平台销量"><div className="grid gap-2 sm:grid-cols-3">{data.platform_columns.map((platform) => <DetailField key={platform} label={`日销 · ${platform}`} value={item.daily_platform_sales[platform]} />)}</div></DetailSection><DetailSection title="年度销量"><div className="grid grid-cols-3 gap-2 sm:grid-cols-5">{annualValues.map((period) => <DetailField key={period} label={`${period}年`} value={item.annual_sales[period]} />)}</div></DetailSection><DetailSection title="月度销量"><div className="grid grid-cols-3 gap-2 sm:grid-cols-5">{monthlyValues.map((period) => <DetailField key={period} label={period} value={item.monthly_sales[period]} />)}</div></DetailSection></TabsContent>
          <TabsContent value="stock" className="space-y-4"><div className="grid gap-3 sm:grid-cols-2"><SummaryMetric icon={Boxes} label="在仓合计" value={item.stock_total} /><SummaryMetric icon={Boxes} label="在途合计" value={item.in_transit_total} /><SummaryMetric icon={Boxes} label="整体库存合计" value={item.inventory_total} /><SummaryMetric icon={Boxes} label="回单" value={metric(item, "return_qty")} /><SummaryMetric icon={Boxes} label="补单合计" value={metric(item, "replenishment_total")} /><SummaryMetric icon={Boxes} label="补单后库存" value={metric(item, "post_replenishment_stock")} /><SummaryMetric icon={Boxes} label="补单后合计" value={metric(item, "post_replenishment_total")} /><SummaryMetric icon={CalendarDays} label="补单后周转天数" value={metric(item, "post_replenishment_turnover_days")} /></div><SizeGrid title="在仓库存" values={item.stock_by_size} sizes={data.size_columns} /><SizeGrid title="在途库存" values={item.in_transit_by_size} sizes={data.size_columns} /><SizeGrid title="库存合计" values={item.inventory_by_size} sizes={data.size_columns} /><SizeGrid title="销售明细" values={item.sales_by_size} sizes={data.size_columns} /><SizeGrid title="补单明细" values={item.replenishment_by_size} sizes={data.size_columns} /><SizeGrid title="补单后尺码" values={item.post_replenishment_by_size} sizes={data.size_columns} /><ManualReplenishmentForm item={item} sizes={data.size_columns} canEdit={canEdit} onSave={onSave} /></TabsContent>
        </div>
      </Tabs>
    </div>
  </div>
}
