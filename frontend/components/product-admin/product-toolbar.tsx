"use client"

import { useEffect, useRef, useState } from "react"
import { History, ImagePlus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { type BrandKey } from "@/lib/brands"
import { assertProductExportAllowed, downloadProductExport, getProductImageRefreshStatus, importProducts, refreshProductImages, type ProductExportProgress } from "@/lib/api"
import type { ProductImageRefreshStatus } from "@/lib/types"

type ProductToolbarProps = {
  brand: BrandKey | "all"
  value: string
  isLoading: boolean
  selectedIds?: Set<number>
  canExport?: boolean
  canImport?: boolean
  canRefreshImages?: boolean
  onValueChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  onRefresh: () => void
  onImportComplete: (skus: string[]) => void
  onCreate?: () => void
  onOpenLogs?: () => void
  onMessage: (title: string, description: string) => void
}

export function ProductToolbar({
  brand,
  value,
  isLoading,
  selectedIds,
  canExport = true,
  canImport = true,
  canRefreshImages = true,
  onValueChange,
  onSearch,
  onClear,
  onRefresh,
  onImportComplete,
  onCreate,
  onOpenLogs,
  onMessage,
}: ProductToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const submittedImageRefreshAtRef = useRef<number | null>(null)
  const [importing, setImporting] = useState(false)
  const [refreshingImages, setRefreshingImages] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportingMode, setExportingMode] = useState<"default" | "with_sizes" | null>(null)
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

  const handleExport = async (mode?: "with_sizes") => {
    const ids = brand !== "all" && selectedIds && selectedIds.size > 0 ? Array.from(selectedIds) : undefined
    setExporting(true)
    setExportingMode(mode ?? "default")
    setExportProgress({ phase: "preparing", loaded: 0, total: null, percent: null })
    try {
      await assertProductExportAllowed(brand, ids, mode)
      await downloadProductExport(brand, ids, mode, setExportProgress)
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

    setImporting(true)
    try {
      const result = await importProducts(brand, file)
      onMessage("导入完成", result.message)
      onClear()
      onImportComplete(result.skus)
    } catch {
      onMessage("导入失败", "请检查文件格式是否正确")
    } finally {
      setImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
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
    : hasSelection ? `导出选中 (${selectedIds!.size})` : "导出 Excel"
  const sizeExportLabel = exportingMode === "with_sizes" && exportStatusText ? exportStatusText : "带尺码导出"
  const lastImageRun = imageRefreshStatus?.last_run
  const imageStatusText = imageRefreshStatus?.in_progress
    ? "图片刷新任务正在后台运行"
    : lastImageRun
      ? `最近刷新：更新 ${lastImageRun.updated ?? 0} 条`
      : "图片刷新将由后台任务执行"

  return (
    <div className="surface-panel flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-1.5">
          <Label htmlFor="product-search-input" className="text-xs text-muted-foreground">
            {hasMultipleLines ? "批量搜索（逗号或换行分隔）" : "货号搜索"}
          </Label>
          <textarea
            id="product-search-input"
            value={value}
            placeholder="输入货号或原始货号，多个可用逗号分隔，Shift+Enter 换行"
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
        <div className="flex gap-2">
          <Button type="button" size="sm" onClick={onSearch} disabled={isLoading} className="cursor-pointer">
            搜索
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClear} disabled={isLoading && value.length === 0} className="cursor-pointer">
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
      <p className="text-xs text-muted-foreground">{imageStatusText}</p>

      {showActions ? (
      <div className="flex items-center gap-2 border-t border-border pt-3">
        {canExport ? (
          <Button type="button" variant="outline" size="sm" onClick={() => void handleExport()} disabled={isLoading || exporting} className="cursor-pointer">
            {defaultExportLabel}
          </Button>
        ) : null}
        {onCreate ? (
          <>
            {canExport ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void handleExport("with_sizes")} disabled={isLoading || exporting} className="cursor-pointer">
                {sizeExportLabel}
              </Button>
            ) : null}
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
            <div className="flex-1" />
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
