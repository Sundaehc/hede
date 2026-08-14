"use client"

import { useEffect, useRef, useState } from "react"
import { History, ImagePlus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { type ProductArchiveBrandKey } from "@/lib/brands"
import { assertProductExportAllowed, downloadProductExport, getProductImageRefreshStatus, importProducts, refreshProductImages, type ProductExportProgress } from "@/lib/api"
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
  const fileInputRef = useRef<HTMLInputElement>(null)
  const submittedImageRefreshAtRef = useRef<number | null>(null)
  const [importing, setImporting] = useState(false)
  const [refreshingImages, setRefreshingImages] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportingMode, setExportingMode] = useState<"default" | "with_sizes" | "today" | "today_with_sizes" | null>(null)
  const [activityDate, setActivityDate] = useState(currentShanghaiDateValue)
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

  const handleExport = async (mode?: "with_sizes", exportActivityDate?: string) => {
    const isActivityExport = Boolean(exportActivityDate)
    const ids = !isActivityExport && brand !== "all" && selectedIds && selectedIds.size > 0 ? Array.from(selectedIds) : undefined
    const exportYear = isActivityExport ? undefined : year || undefined
    const exportQuery = !isActivityExport && !ids ? query || undefined : undefined
    const exportSkuPrefix = !isActivityExport && !ids ? skuPrefix || undefined : undefined
    setExporting(true)
    setExportingMode(isActivityExport ? (mode ? "today_with_sizes" : "today") : (mode ?? "default"))
    setExportProgress({ phase: "preparing", loaded: 0, total: null, percent: null })
    try {
      await assertProductExportAllowed(brand, ids, mode, exportActivityDate, exportYear, exportQuery, exportSkuPrefix)
      await downloadProductExport(brand, ids, mode, setExportProgress, exportActivityDate, exportYear, exportQuery, exportSkuPrefix)
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

  const hasMultipleLines = value.includes("\n") || value.includes(",") || value.includes("，")
  const hasSelection = brand !== "all" && selectedIds && selectedIds.size > 0
  const showActions = canExport || onCreate
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
  const activityExportLabel = exportingMode === "today" && exportStatusText ? exportStatusText : "导出当日导入/新增"
  const activitySizeExportLabel = exportingMode === "today_with_sizes" && exportStatusText ? exportStatusText : "导出当日导入/新增带尺码"
  const lastImageRun = imageRefreshStatus?.last_run
  const imageStatusText = imageRefreshStatus?.in_progress
    ? "图片刷新任务正在后台运行"
    : lastImageRun
      ? `最近刷新：更新 ${lastImageRun.updated ?? 0} 条`
      : "图片刷新将由后台任务执行"

  return (
    <div className="surface-panel flex flex-col gap-3 p-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
        <div className="min-w-0">
          <div className="grid gap-3 md:grid-cols-[minmax(20rem,1.65fr)_minmax(14rem,0.8fr)]">
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="product-search-input" className="text-xs text-muted-foreground">
              {hasMultipleLines ? "包含搜索（逗号或换行分隔）" : "包含搜索"}
            </Label>
            <textarea
              id="product-search-input"
              value={value}
              placeholder="货号或原始货号，多个可用逗号分隔，Shift+Enter 换行"
              rows={hasMultipleLines ? 3 : 1}
              onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => onValueChange(event.target.value)}
              onKeyDown={(event: React.KeyboardEvent<HTMLTextAreaElement>) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault()
                  onSearch()
                }
              }}
              className="resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="product-sku-prefix-input" className="text-xs text-muted-foreground">
              货号前缀
            </Label>
            <input
              id="product-sku-prefix-input"
              value={prefixValue}
              placeholder="货号/原始货号开头"
              onChange={(event) => onPrefixValueChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault()
                  onSearch()
                }
              }}
              className="h-9 rounded-lg border border-input bg-card px-3 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{imageStatusText}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 xl:justify-end xl:self-center">
          <Button type="button" size="sm" onClick={onSearch} disabled={isLoading} className="cursor-pointer">
            搜索
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClear} disabled={isLoading && value.length === 0 && prefixValue.length === 0} className="cursor-pointer">
            清空
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onRefresh} disabled={isLoading} className="cursor-pointer">
            刷新
          </Button>
          {onOpenLogs ? (
            <Button type="button" variant="outline" size="sm" onClick={onOpenLogs} className="cursor-pointer">
              <History className="h-3.5 w-3.5" />
              操作日志
            </Button>
          ) : null}
          {onOpenRecycleBin ? (
            <Button type="button" variant="outline" size="sm" onClick={onOpenRecycleBin} className="cursor-pointer">
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
              className="cursor-pointer"
              title={brand === "all" ? "提交全部品牌图片刷新任务" : "提交当前品牌图片刷新任务"}
            >
              <ImagePlus className="h-3.5 w-3.5" />
              {imageRefreshStatus?.in_progress ? "后台刷新中..." : refreshingImages ? "提交中..." : "刷新图片"}
            </Button>
          ) : null}
        </div>
      </div>

      {showActions ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
          {canExport ? (
            <>
              <Button type="button" variant="outline" size="sm" onClick={() => void handleExport()} disabled={isLoading || exporting} className="cursor-pointer">
                {defaultExportLabel}
              </Button>
              {onCreate ? (
                <Button type="button" variant="outline" size="sm" onClick={() => void handleExport("with_sizes")} disabled={isLoading || exporting} className="cursor-pointer">
                  {sizeExportLabel}
                </Button>
              ) : null}
              <div className="flex items-center gap-1.5">
                <Label htmlFor="product-activity-export-date" className="whitespace-nowrap text-xs text-muted-foreground">导出日期</Label>
                <input
                  id="product-activity-export-date"
                  type="date"
                  value={activityDate}
                  onChange={(event) => setActivityDate(event.target.value)}
                  disabled={isLoading || exporting}
                  className="h-8 cursor-pointer rounded-md border border-input bg-card px-2 text-xs shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <Button type="button" variant="outline" size="sm" onClick={() => void handleExport(undefined, activityDate)} disabled={isLoading || exporting || !activityDate} className="cursor-pointer">
                  {activityExportLabel}
                </Button>
                {onCreate ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => void handleExport("with_sizes", activityDate)} disabled={isLoading || exporting || !activityDate} className="cursor-pointer">
                    {activitySizeExportLabel}
                  </Button>
                ) : null}
              </div>
            </>
          ) : null}
          {onCreate ? (
            <>
              <div className="flex-1" />
              {canImport ? (
                <>
                  <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={importing} className="cursor-pointer">
                    {importing ? "导入中..." : "导入 Excel"}
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.xls"
                    className="hidden"
                    onChange={(e) => void handleImport(e)}
                  />
                </>
              ) : null}
              <Button type="button" size="sm" onClick={onCreate} className="cursor-pointer">
                <span>新增商品</span>
              </Button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
