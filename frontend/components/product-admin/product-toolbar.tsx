"use client"

import { useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { type BrandKey } from "@/lib/brands"
import { exportProducts, importProducts } from "@/lib/api"

type ProductToolbarProps = {
  brand: BrandKey
  value: string
  isLoading: boolean
  onValueChange: (value: string) => void
  onSearch: () => void
  onClear: () => void
  onRefresh: () => void
  onCreate: () => void
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
}: ProductToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

  const handleExport = async () => {
    try {
      const response = await exportProducts(brand)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${brand}_products.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert("导出失败")
    }
  }

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setImporting(true)
    try {
      const result = await importProducts(brand, file)
      alert(result.message)
      onRefresh()
    } catch {
      alert("导入失败，请检查文件格式")
    } finally {
      setImporting(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 md:flex-row md:items-end md:justify-between">
      <div className="flex flex-1 flex-col gap-2">
        <Label htmlFor="product-search-input">原始货号</Label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id="product-search-input"
            value={value}
            placeholder="请输入原始货号"
            onChange={(event) => onValueChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                onSearch()
              }
            }}
          />
          <div className="flex flex-1 gap-2">
            <Button type="button" onClick={onSearch} disabled={isLoading} className="cursor-pointer">
              搜索
            </Button>
            <Button type="button" variant="outline" onClick={onClear} disabled={isLoading && value.length === 0} className="cursor-pointer">
              清空
            </Button>
            <Button type="button" variant="outline" onClick={onRefresh} disabled={isLoading} className="cursor-pointer">
              刷新
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={handleExport} disabled={isLoading} className="cursor-pointer">
          导出 Excel
        </Button>
        <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()} disabled={importing} className="cursor-pointer">
          {importing ? "导入中..." : "导入 Excel"}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          onChange={(e) => void handleImport(e)}
        />
        <Button type="button" variant="secondary" onClick={onCreate} className="cursor-pointer">
          新增商品
        </Button>
      </div>
    </div>
  )
}
