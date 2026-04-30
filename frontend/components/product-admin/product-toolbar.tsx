"use client"

import { useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { type BrandKey } from "@/lib/brands"
import { exportProducts, importProducts } from "@/lib/api"

type ProductToolbarProps = {
  brand: BrandKey | "all"
  value: string
  isLoading: boolean
  onValueChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  onRefresh: () => void
  onCreate?: () => void
  onMessage: (title: string, description: string) => void
}

export function ProductToolbar({
  brand,
  value,
  isLoading,
  onValueChange,
  onSearch,
  onClear,
  onRefresh,
  onCreate,
  onMessage,
}: ProductToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

  const handleExport = async () => {
    try {
      const response = await exportProducts(brand)
      const disposition = response.headers.get("Content-Disposition") ?? ""
      const match = disposition.match(/filename\*=UTF-8''(.+)/)
      const filename = match ? decodeURIComponent(match[1]) : `${brand}_products.xlsx`
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      onMessage("导出失败", "导出 Excel 时发生错误，请重试")
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
    } catch {
      onMessage("导入失败", "请检查文件格式是否正确")
    } finally {
      setImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
  }

  const hasMultipleLines = value.includes("\n") || value.includes(",") || value.includes("，")

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-1.5">
          <Label htmlFor="product-search-input" className="text-xs text-muted-foreground">
            {hasMultipleLines ? "批量搜索（逗号或换行分隔）" : "货号搜索"}
          </Label>
          <textarea
            id="product-search-input"
            value={value}
            placeholder="输入货号或原始货号，多个可用逗号或换行分隔"
            rows={hasMultipleLines ? 3 : 1}
            onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => onValueChange(event.target.value)}
            onKeyDown={(event: React.KeyboardEvent<HTMLTextAreaElement>) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                onSearch()
              }
            }}
            className="resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
        <div className="flex gap-2 pb-0.5">
          <Button type="button" size="sm" onClick={onSearch} disabled={isLoading} className="cursor-pointer">
            搜索
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClear} disabled={isLoading && value.length === 0} className="cursor-pointer">
            清空
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onRefresh} disabled={isLoading} className="cursor-pointer">
            刷新
          </Button>
        </div>
      </div>

      {onCreate ? (
        <div className="flex items-center gap-2 border-t border-border pt-3">
          <Button type="button" variant="outline" size="sm" onClick={handleExport} disabled={isLoading} className="cursor-pointer">
            导出 Excel
          </Button>
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
          <div className="flex-1" />
          <Button type="button" variant="secondary" size="sm" onClick={onCreate} className="cursor-pointer">
            新增商品
          </Button>
        </div>
      ) : null}
    </div>
  )
}
