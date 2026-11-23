"use client"

import { useState } from "react"
import { ChevronLeft, ChevronRight, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { getSeasonalItemReview } from "@/lib/api"
import type { SeasonalFilters, SeasonalItem } from "@/lib/seasonal-analysis"
import {
  STOCK_SOURCE_RESOURCES,
  useStockModuleQuery,
} from "@/lib/stock-module-query"
import { StockProductPhoto } from "./stock-product-photo"

const formatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 })
const units = (value: number | string | null) =>
  value == null ? "—" : `${formatter.format(Number(value))} 双`

export function SeasonalItemReviewDialog({
  item,
  filters,
  stockDate,
  revision,
  onClose,
}: {
  item: SeasonalItem
  filters: Pick<SeasonalFilters, "brand" | "year" | "quarter">
  stockDate: string | null
  revision: number
  onClose: () => void
}) {
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const { data, previousData, error, refreshing } = useStockModuleQuery({
    group: "seasonal-item-review",
    queryKey: JSON.stringify([
      filters.brand,
      filters.year,
      filters.quarter,
      item.id,
      page,
      revision,
    ]),
    revision: retry,
    resources: STOCK_SOURCE_RESOURCES,
    load: (signal) => getSeasonalItemReview(filters, item.id, page, signal),
  })
  const detail = data ?? previousData
  const receipts = detail?.receipts
  const sales = detail?.sales
  const milestones = [
    ["首次采购入库", detail?.first_inbound_date ?? "—"],
    ["档案上市", item.launch_date ?? "待核对"],
    [
      "观察期内首销",
      sales?.first_sale_date ??
        (sales?.missing_days === 0 ? "未见正向销售" : "—"),
    ],
    ["当前可售库存", units(item.available_quantity)],
  ]

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-4xl overflow-y-auto p-0">
        <DialogHeader className="flex-row items-center gap-3 border-b px-5 py-4 pr-14 sm:gap-4 sm:px-6 sm:pr-16">
          <StockProductPhoto item={item} detail />
          <div className="min-w-0 space-y-1">
            <DialogTitle>单款复盘 · {item.sku}</DialogTitle>
            <DialogDescription>
              {[
                item.product_name,
                item.color,
                `${filters.year} 年 Q${filters.quarter}`,
                stockDate && `库存 ${stockDate}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </DialogDescription>
          </div>
        </DialogHeader>
        <DialogClose
          className="absolute top-4 right-4 inline-flex size-8 items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="关闭复盘"
        >
          <X className="size-4" aria-hidden="true" />
        </DialogClose>
        <div
          className="space-y-5 px-5 pb-5 sm:px-6 sm:pb-6"
          aria-busy={refreshing}
        >
          <dl className="grid grid-cols-2 divide-x rounded-lg border bg-muted/30 sm:grid-cols-4">
            {milestones.map(([label, value]) => (
              <div key={label} className="min-w-0 px-3 py-3 sm:px-4">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1.5 text-sm font-semibold tabular-nums">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {refreshing && (
            <p role="status" className="text-xs text-muted-foreground">
              正在读取复盘数据…
            </p>
          )}
          {error && (
            <div
              role="alert"
              className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive"
            >
              {error}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRetry((value) => value + 1)}
              >
                重试
              </Button>
            </div>
          )}
          {detail && (
            <div className="grid items-start gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
              <section
                aria-label="各渠道销量"
                className="overflow-hidden rounded-lg border"
              >
                <div className="space-y-1 px-4 py-3">
                  <h3 className="text-sm font-semibold">各渠道销量</h3>
                  <p className="text-xs text-muted-foreground">
                    {sales?.start && sales.end && sales.start <= sales.end
                      ? `${sales.start} 至 ${sales.end}`
                      : "销售观察期未就绪"}
                  </p>
                </div>
                {sales?.missing_days == null || sales.missing_days > 0 ? (
                  <p className="border-t px-4 py-3 text-xs text-muted-foreground">
                    {sales?.missing_days
                      ? `日销缺少 ${sales.missing_days} 天，渠道合计暂不可核实。`
                      : "日销来源或商品匹配未就绪。"}
                  </p>
                ) : sales.channels.length ? (
                  <table className="w-full text-left text-xs">
                    <thead className="border-y bg-muted/40 text-muted-foreground">
                      <tr>
                        <th scope="col" className="px-4 py-2 font-medium">
                          渠道
                        </th>
                        <th
                          scope="col"
                          className="px-3 py-2 text-right font-medium"
                        >
                          销售
                        </th>
                        <th
                          scope="col"
                          className="px-4 py-2 text-right font-medium"
                        >
                          净销
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {sales.channels.map((row) => (
                        <tr key={row.channel}>
                          <td className="px-4 py-2">{row.channel}</td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {formatter.format(row.gross_sales)}
                          </td>
                          <td className="px-4 py-2 text-right tabular-nums">
                            {formatter.format(row.net_sales)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="border-t px-4 py-3 text-xs text-muted-foreground">
                    观察期内暂无销售或退回记录。
                  </p>
                )}
                <p className="border-t px-4 py-2 text-xs text-muted-foreground">
                  按原始日销和现有渠道映射统计，同款同日唯品与聚水潭去重。售出后同日全退的记录仍计入销售，可能与季度汇总有差异；唯品未单列退货。
                </p>
              </section>
              <section
                aria-label="本季采购入库明细"
                className="overflow-hidden rounded-lg border"
              >
                <div className="space-y-1 px-4 py-3">
                  <h3 className="text-sm font-semibold">
                    本季采购入库明细
                    {receipts && ` · ${units(receipts.quantity)}`}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {detail.receipt_end
                      ? `截至 ${detail.receipt_end} · 同日同入仓单及采购单的尺码数量合并`
                      : "入库统计日期未就绪"}
                  </p>
                </div>
                {receipts?.items.length ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-y bg-muted/40 text-muted-foreground">
                        <tr>
                          <th
                            scope="col"
                            className="px-4 py-2 font-medium whitespace-nowrap"
                          >
                            入库日期
                          </th>
                          {detail.show_receipt_numbers && (
                            <>
                              <th
                                scope="col"
                                className="px-3 py-2 font-medium whitespace-nowrap"
                              >
                                入仓单号
                              </th>
                              <th
                                scope="col"
                                className="px-3 py-2 font-medium whitespace-nowrap"
                              >
                                采购单号
                              </th>
                            </>
                          )}
                          <th
                            scope="col"
                            className="px-4 py-2 text-right font-medium whitespace-nowrap"
                          >
                            双数
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {receipts.items.map((row, index) => (
                          <tr key={`${receipts.page}-${index}`}>
                            <td className="px-4 py-2 whitespace-nowrap tabular-nums">
                              {row.inbound_date}
                            </td>
                            {detail.show_receipt_numbers && (
                              <>
                                <td className="px-3 py-2 break-all">
                                  {row.inbound_id || "未提供"}
                                </td>
                                <td className="px-3 py-2 break-all">
                                  {row.purchase_order_id || "未提供"}
                                </td>
                              </>
                            )}
                            <td className="px-4 py-2 text-right tabular-nums">
                              {formatter.format(Number(row.quantity))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="border-t px-4 py-3 text-xs text-muted-foreground">
                    {receipts
                      ? "本季暂无符合口径的采购入库。"
                      : "采购入库数据未就绪。"}
                  </p>
                )}
                {receipts && (
                  <div className="flex items-center justify-between gap-2 border-t px-4 py-2 text-xs text-muted-foreground">
                    <span>
                      共 {receipts.total} 笔
                      {!detail.show_receipt_numbers && " · 单号需库存查看权限"}
                    </span>
                    {receipts.pages > 1 && (
                      <div className="flex items-center gap-2">
                        <Button
                          size="icon"
                          variant="outline"
                          className="size-7"
                          aria-label="上一页入库明细"
                          disabled={refreshing || receipts.page <= 1}
                          onClick={() => setPage(receipts.page - 1)}
                        >
                          <ChevronLeft className="size-4" aria-hidden="true" />
                        </Button>
                        <span className="tabular-nums">
                          {receipts.page} / {receipts.pages}
                        </span>
                        <Button
                          size="icon"
                          variant="outline"
                          className="size-7"
                          aria-label="下一页入库明细"
                          disabled={
                            refreshing || receipts.page >= receipts.pages
                          }
                          onClick={() => setPage(receipts.page + 1)}
                        >
                          <ChevronRight className="size-4" aria-hidden="true" />
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </section>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
