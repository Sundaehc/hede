"use client"

import { useSessionQueryState } from "@/lib/session-query-state"

import { useEffect, useId, useRef, useState } from "react"
import { BadgeDollarSign, ChevronDown, FileDown, FileSpreadsheet, History, ImagePlus, Plus, Ruler, Search, Trash2, Upload } from "lucide-react"

import { Button } from "@/components/ui/button"
import { DateRangeControl } from "@/components/ui/date-range-control"
import { Label } from "@/components/ui/label"
import { type ProductArchiveBrandKey } from "@/lib/brands"
import { assertProductExportAllowed, downloadProductExport, downloadProductImportTemplate, getProductImageRefreshStatus, importProducts, refreshProductImages, type ProductExportMode, type ProductExportProgress } from "@/lib/api"
import type { ProductImageRefreshStatus } from "@/lib/types"

type ProductToolbarProps = {
  brand: ProductArchiveBrandKey
  year: string
  value: string
  query: string
  prefixValue: string
  skuPrefix: string
  isLoading: boolean
  selectedIds?: Set<number>
  canExport?: boolean
  canExportPrices?: boolean
  canImport?: boolean
  canRefreshImages?: boolean
  onValueChange: (value: string) => void
  onPrefixValueChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  onRefresh: () => void
  onImportComplete: (skus: string[]) => void
  onCreate?: () => void
  onOpenLogs?: () => void
  onOpenRecycleBin?: () => void
  onMessage: (title: string, description: string) => void
}

function currentShanghaiDateValue() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

export function ProductToolbar({
  brand,
  year,
  value,
  query,
  prefixValue,
  skuPrefix,
  isLoading,
  selectedIds,
  canExport = true,
  canExportPrices = false,
  canImport = true,
  canRefreshImages = true,
  onValueChange,
  onPrefixValueChange,
  onSearch,
  onClear,
  onRefresh,
  onImportComplete,
  onCreate,
  onOpenLogs,
  onOpenRecycleBin,
  onMessage,
}: ProductToolbarProps) {
  const currentDate = currentShanghaiDateValue()
  const toolbarContentId = useId()
  const activityExportDescriptionId = useId()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const submittedImageRefreshAtRef = useRef<number | null>(null)
  const [importing, setImporting] = useState(false)
  const [downloadingTemplate, setDownloadingTemplate] = useState(false)
  const [refreshingImages, setRefreshingImages] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportingMode, setExportingMode] = useState<"default" | ProductExportMode | "range" | "range_with_sizes" | null>(null)
  const [isExpanded, setIsExpanded] = useSessionQueryState("products-toolbar:expanded", true)
  const [activityDateStart, setActivityDateStart] = useSessionQueryState("products-toolbar:activityDateStart", currentShanghaiDateValue)
  const [activityDateEnd, setActivityDateEnd] = useSessionQueryState("products-toolbar:activityDateEnd", currentShanghaiDateValue)
  const [exportProgress, setExportProgress] = useState<ProductExportProgress | null>(null)
  const [awaitingImageRefresh, setAwaitingImageRefresh] = useState(false)
  const [imageRefreshStatus, setImageRefreshStatus] = useState<ProductImageRefreshStatus | null>(null)

  const loadImageRefreshStatus = async () => {
    try {
      setImageRefreshStatus(await getProductImageRefreshStatus())
    } catch {
      setImageRefreshStatus(null)
    }
  }

  useEffect(() => {
    void loadImageRefreshStatus()
  }, [])

  useEffect(() => {
    if (!imageRefreshStatus?.in_progress) {
      return
    }

    const timer = window.setInterval(() => {
      void loadImageRefreshStatus()
    }, 5000)

    return () => window.clearInterval(timer)
  }, [imageRefreshStatus?.in_progress])

  useEffect(() => {
    if (!awaitingImageRefresh || !imageRefreshStatus || imageRefreshStatus.in_progress) {
      return
    }

    const lastRun = imageRefreshStatus.last_run
    const submittedAt = submittedImageRefreshAtRef.current
    const finishedAt = lastRun?.finished_at ? Date.parse(lastRun.finished_at) : 0
    if (!lastRun || !submittedAt || finishedAt < submittedAt) {
      return
    }

    setAwaitingImageRefresh(false)
    submittedImageRefreshAtRef.current = null

    if (lastRun.status === "completed") {
      onMessage("图片刷新完成", lastRun.message)
      onRefresh()
      return
    }

    if (lastRun.status === "failed") {
      onMessage("图片刷新失败", lastRun.error || lastRun.message)
    }
  }, [awaitingImageRefresh, imageRefreshStatus, onMessage, onRefresh])

  const handleExport = async (mode?: ProductExportMode, exportActivityDateStart?: string, exportActivityDateEnd?: string) => {
    const isActivityExport = Boolean(exportActivityDateStart || exportActivityDateEnd)
    if (isActivityExport && (!exportActivityDateStart || !exportActivityDateEnd)) {
      onMessage("请选择导出时间段", "开始日期和结束日期都需要填写")
      return
    }
    if (exportActivityDateStart && exportActivityDateEnd && exportActivityDateStart > exportActivityDateEnd) {
      onMessage("导出时间段无效", "结束日期不能早于开始日期")
      return
    }
    if ((exportActivityDateStart && exportActivityDateStart > currentDate) || (exportActivityDateEnd && exportActivityDateEnd > currentDate)) {
      onMessage("导出时间段无效", "不能选择未来日期")
      return
    }
    const ids = !isActivityExport && brand !== "all" && selectedIds && selectedIds.size > 0 ? Array.from(selectedIds) : undefined
    const exportYear = isActivityExport ? undefined : year || undefined
    const exportQuery = !isActivityExport && !ids ? query || undefined : undefined
    const exportSkuPrefix = !isActivityExport && !ids ? skuPrefix || undefined : undefined
    setExporting(true)
    setExportingMode(isActivityExport ? (mode ? "range_with_sizes" : "range") : (mode ?? "default"))
    setExportProgress({ phase: "preparing", loaded: 0, total: null, percent: null })
    try {
      await assertProductExportAllowed(brand, ids, mode, exportActivityDateStart, exportActivityDateEnd, exportYear, exportQuery, exportSkuPrefix)
      await downloadProductExport(brand, ids, mode, setExportProgress, exportActivityDateStart, exportActivityDateEnd, exportYear, exportQuery, exportSkuPrefix)
    } catch (error) {
      onMessage("导出失败", error instanceof Error ? error.message : "导出 Excel 时发生错误，请重试")
    } finally {
      setExporting(false)
      setExportingMode(null)
      setExportProgress(null)
    }
  }

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (brand === "all") {
      onMessage("导入失败", "请选择具体品牌后再导入")
      return
    }

    setImporting(true)
    let importedSkus: string[] = []
    try {
      const result = await importProducts(brand, file)
      importedSkus = result.skus
      onMessage("导入完成", result.message)
    } catch (error) {
      onMessage("导入失败", error instanceof Error ? error.message : "导入时发生未知错误，请重试")
      return
    } finally {
      setImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }

    onClear()
    onImportComplete(importedSkus)
  }

  const handleDownloadTemplate = async () => {
    setDownloadingTemplate(true)
    try {
      await downloadProductImportTemplate()
    } catch (error) {
      onMessage("下载失败", error instanceof Error ? error.message : "下载导入模板时发生错误，请重试")
    } finally {
      setDownloadingTemplate(false)
    }
  }

  const handleRefreshImages = async () => {
    setRefreshingImages(true)
    try {
      const result = await refreshProductImages(brand)
      onMessage(result.accepted ? "图片刷新已启动" : "图片刷新进行中", result.message)
      if (result.accepted || result.in_progress) {
        submittedImageRefreshAtRef.current = Date.now()
        setAwaitingImageRefresh(true)
        setImageRefreshStatus((current) => ({
          ...(result.status ?? current ?? {}),
          in_progress: true,
        }))
      } else if (result.status) {
        setImageRefreshStatus(result.status)
      }
    } catch {
      onMessage("图片刷新失败", "刷新图片路径时发生错误，请确认图片共享目录可访问")
    } finally {
      setRefreshingImages(false)
    }
  }

  const searchRows = Math.min(3, value.split("\n").length)
  const hasSelection = brand !== "all" && selectedIds && selectedIds.size > 0
  const showActions = canExport || canExportPrices || onCreate
  const exportStatusText = exportProgress?.phase === "preparing"
    ? "准备导出..."
    : exportProgress?.percent !== null && exportProgress?.percent !== undefined
      ? `导出 ${exportProgress.percent}%`
      : exporting
        ? "导出中..."
        : null
  const defaultExportLabel = exportingMode === "default" && exportStatusText
    ? exportStatusText
    : hasSelection ? `导出选中 (${selectedIds!.size})` : query || skuPrefix ? "导出搜索结果" : "导出 Excel"
  const sizeExportLabel = exportingMode === "with_sizes" && exportStatusText ? exportStatusText : "带尺码导出"
  const priceExportLabel = exportingMode === "price" && exportStatusText ? exportStatusText : "物价导出"
  const activityExportLabel = exportingMode === "range" && exportStatusText ? exportStatusText : "导出记录"
  const activitySizeExportLabel = exportingMode === "range_with_sizes" && exportStatusText ? exportStatusText : "导出记录（含尺码）"
  const lastImageRun = imageRefreshStatus?.last_run
  const imageStatusText = imageRefreshStatus?.in_progress
    ? "图片刷新任务正在后台运行"
    : lastImageRun
      ? `最近刷新：更新 ${lastImageRun.updated ?? 0} 条`
      : "图片刷新将由后台任务执行"
  const activeSearchFilters = [
    { label: "包含", value: query.trim().replace(/\s+/g, " ") },
    { label: "前缀", value: skuPrefix.trim() },
  ].filter((filter) => filter.value)
  const collapsedSearchSummary = activeSearchFilters.map((filter) => `${filter.label}：${filter.value}`).join("；")

  return (
    <div className={`surface-panel flex min-w-0 flex-col px-3 py-2 ${isExpanded ? "gap-2" : ""}`}>
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span aria-hidden="true" className="hidden size-6 shrink-0 items-center justify-center rounded-md bg-muted/70 text-muted-foreground sm:flex">
            <Search className="size-3.5" />
          </span>
          <span className="shrink-0 text-xs font-medium text-foreground">搜索与导出</span>
          {isExpanded && canRefreshImages ? (
            <span role="status" className="truncate border-l border-border pl-2 text-[11px] text-muted-foreground" title={imageStatusText}>{imageStatusText}</span>
          ) : null}
          {!isExpanded ? (
            activeSearchFilters.length > 0 ? (
              <>
                <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground">
                  {activeSearchFilters.length} 项条件
                </span>
                <div role="group" aria-label="当前搜索条件" title={collapsedSearchSummary} className="hidden min-w-0 items-center gap-1.5 sm:flex">
                  {activeSearchFilters.map((filter) => (
                    <span key={filter.label} title={`${filter.label}：${filter.value}`} className="inline-flex min-w-0 max-w-64 items-center gap-1 rounded-md border border-border/70 bg-muted/30 px-1.5 py-0.5 text-[11px]">
                      <span className="shrink-0 text-muted-foreground">{filter.label}</span>
                      <span className="truncate font-medium text-foreground">{filter.value}</span>
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <span className="hidden truncate text-[11px] text-muted-foreground sm:inline">未设置搜索条件</span>
            )
          ) : null}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={isExpanded}
          aria-controls={toolbarContentId}
          onClick={() => setIsExpanded((expanded) => !expanded)}
          title={isExpanded ? "收起搜索与导出工具，保留当前搜索条件" : "展开搜索与导出工具"}
          className="h-7 shrink-0 cursor-pointer gap-2 rounded-md border-border/80 bg-background px-2.5 text-xs text-muted-foreground shadow-none hover:border-foreground/25 hover:bg-muted/70 hover:text-foreground aria-expanded:bg-background aria-expanded:text-muted-foreground"
        >
          {isExpanded ? "收起搜索区" : "展开搜索区"}
          <span aria-hidden="true" className="h-3 w-px bg-border" />
          <ChevronDown aria-hidden="true" className={`size-3.5 transition-transform duration-200 motion-reduce:transition-none ${isExpanded ? "rotate-180" : "rotate-0"}`} />
        </Button>
      </div>
      <div id={toolbarContentId} hidden={!isExpanded} className={isExpanded ? "flex min-w-0 flex-col gap-2" : "hidden"}>
        <div className="grid min-w-0 gap-2 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
          <div className="grid min-w-0 gap-2 sm:grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)]">
            <div className="relative min-w-0">
              <Label htmlFor="product-search-input" className="sr-only">
                包含搜索
              </Label>
              <Search aria-hidden="true" className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
              <textarea
                id="product-search-input"
                value={value}
                placeholder="货号/原始货号，逗号分隔多个"
                title="支持逗号或换行分隔多个货号，Enter 搜索，Shift+Enter 换行"
                rows={searchRows}
                onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => onValueChange(event.target.value)}
                onKeyDown={(event: React.KeyboardEvent<HTMLTextAreaElement>) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault()
                    onSearch()
                  }
                }}
                className="block max-h-24 min-h-8 w-full min-w-0 resize-none rounded-md border border-input bg-card py-1 pr-2.5 pl-8 text-sm leading-5 shadow-none outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <div className="min-w-0">
              <Label htmlFor="product-sku-prefix-input" className="sr-only">
                货号前缀
              </Label>
              <input
                id="product-sku-prefix-input"
                value={prefixValue}
                placeholder="前缀：货号/原始货号"
                onChange={(event) => onPrefixValueChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    onSearch()
                  }
                }}
                className="h-8 w-full min-w-0 rounded-md border border-input bg-card px-2.5 text-sm shadow-none outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 lg:justify-end">
            <Button type="button" size="sm" onClick={onSearch} disabled={isLoading} className="h-8 cursor-pointer rounded-md shadow-none">
              搜索
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onClear} disabled={isLoading && value.length === 0 && prefixValue.length === 0} className="h-8 cursor-pointer rounded-md shadow-none">
              清空
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onRefresh} disabled={isLoading} className="h-8 cursor-pointer rounded-md shadow-none">
              刷新
            </Button>
            {onOpenLogs ? (
              <Button type="button" variant="outline" size="sm" onClick={onOpenLogs} className="h-8 cursor-pointer rounded-md shadow-none">
                <History className="h-3.5 w-3.5" />
                操作日志
              </Button>
            ) : null}
            {onOpenRecycleBin ? (
              <Button type="button" variant="outline" size="sm" onClick={onOpenRecycleBin} className="h-8 cursor-pointer rounded-md shadow-none">
                <Trash2 className="h-3.5 w-3.5" />
                回收站
              </Button>
            ) : null}
            {canRefreshImages ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void handleRefreshImages()}
                disabled={refreshingImages || imageRefreshStatus?.in_progress}
                className="h-8 cursor-pointer rounded-md shadow-none"
                title={`${brand === "all" ? "提交全部品牌图片刷新任务" : "提交当前品牌图片刷新任务"}；${imageStatusText}`}
              >
                <ImagePlus className="h-3.5 w-3.5" />
                {imageRefreshStatus?.in_progress ? "后台刷新中..." : refreshingImages ? "提交中..." : "刷新图片"}
              </Button>
            ) : null}
          </div>
        </div>

        {showActions ? (
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 border-t border-border pt-2">
            {canExport || canExportPrices ? (
              <div role="group" aria-label="数据导出" className="flex min-w-0 flex-wrap items-center gap-1.5">
                {canExport ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => void handleExport()} disabled={isLoading || exporting} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                    <FileSpreadsheet aria-hidden="true" />
                    {defaultExportLabel}
                  </Button>
                ) : null}
                {canExportPrices ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => void handleExport("price")} disabled={isLoading || exporting} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none" title="导出货号、商品全名、主供应商、预设售价（成本）、工厂货号；优先导出勾选商品，否则导出当前筛选结果">
                    <BadgeDollarSign aria-hidden="true" />
                    {priceExportLabel}
                  </Button>
                ) : null}
                {canExport && onCreate ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => void handleExport("with_sizes")} disabled={isLoading || exporting} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                    <Ruler aria-hidden="true" />
                    {sizeExportLabel}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {onCreate ? (
              <div role="group" aria-label="商品维护" className="flex min-w-0 flex-wrap items-center gap-1.5">
                {canImport ? (
                  <>
                    <Button type="button" variant="outline" size="sm" onClick={() => void handleDownloadTemplate()} disabled={downloadingTemplate || importing} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                      <FileDown aria-hidden="true" />
                      {downloadingTemplate ? "下载中..." : "下载导入模板"}
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={importing} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                      <Upload aria-hidden="true" />
                      {importing ? "导入中..." : "导入 Excel"}
                    </Button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".xlsx,.xls"
                      className="hidden"
                      onChange={(event) => void handleImport(event)}
                    />
                  </>
                ) : null}
                <Button type="button" size="sm" onClick={onCreate} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                  <Plus aria-hidden="true" />
                  新增商品
                </Button>
              </div>
            ) : null}
            {canExport ? (
              <div role="group" aria-label="按时间导出" aria-describedby={activityExportDescriptionId} className="flex min-w-0 max-w-full flex-wrap items-center gap-1.5">
                <span className="shrink-0 text-[11px] text-muted-foreground" title="仅包含所选时间内导入或新增的商品">按时间</span>
                <span id={activityExportDescriptionId} className="sr-only">仅包含所选时间内导入或新增的商品</span>
                <DateRangeControl label="导出时间段" hideLabel size="sm" start={activityDateStart} end={activityDateEnd} onStartChange={setActivityDateStart} onEndChange={setActivityDateEnd} maxDate={currentDate} disabled={isLoading || exporting} />
                <div className="flex flex-wrap items-center gap-1.5">
                  <Button type="button" variant="outline" size="sm" onClick={() => void handleExport(undefined, activityDateStart, activityDateEnd)} disabled={isLoading || exporting || !activityDateStart || !activityDateEnd} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                    <FileDown aria-hidden="true" />
                    {activityExportLabel}
                  </Button>
                  {onCreate ? (
                    <Button type="button" variant="outline" size="sm" onClick={() => void handleExport("with_sizes", activityDateStart, activityDateEnd)} disabled={isLoading || exporting || !activityDateStart || !activityDateEnd} className="h-8 cursor-pointer gap-1.5 rounded-md px-2.5 shadow-none">
                      <Ruler aria-hidden="true" />
                      {activitySizeExportLabel}
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
