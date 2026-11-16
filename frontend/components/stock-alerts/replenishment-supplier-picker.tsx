"use client"

import { useState } from "react"
import { ChevronRight, Search } from "lucide-react"
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

export function ReplenishmentSupplierPicker({
  brandLabel,
  suppliers,
  loading,
  error,
  onSelect,
  onClose,
}: {
  brandLabel: string
  suppliers: string[]
  loading: boolean
  error: string | null
  onSelect: (supplier: string) => void
  onClose: () => void
}) {
  const [query, setQuery] = useState("")
  const search = query.trim().toLocaleLowerCase()
  const matches = suppliers.filter((supplier) =>
    supplier.toLocaleLowerCase().includes(search)
  )

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="flex max-h-[85vh] flex-col gap-4 sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>选择供应商设置规则</DialogTitle>
          <DialogDescription>
            {brandLabel} · 选择供应商，填写交期、合计起订量和尺码配比。
          </DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            aria-label="搜索规则供应商"
            placeholder="输入供应商名称搜索"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="pl-9"
          />
        </div>
        <p className="text-xs text-muted-foreground" role="status">
          {loading
            ? "正在加载供应商…"
            : `当前品牌共 ${suppliers.length} 家供应商${search ? `，匹配 ${matches.length} 家` : ""}，不受商品列表筛选影响。`}
        </p>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border [scrollbar-gutter:stable]">
          {loading || error || !matches.length ? (
            <p
              role={error ? "alert" : undefined}
              className="px-4 py-8 text-center text-sm text-muted-foreground"
            >
              {loading
                ? "正在读取供应商，请稍候…"
                : error
                  ? `供应商读取失败：${error}。请关闭后刷新重试。`
                  : suppliers.length
                    ? "未找到匹配的供应商，请更换关键词。"
                    : "当前品牌暂无可配置的供应商，请先在商品信息档案中填写供应商。"}
            </p>
          ) : (
            <ul className="divide-y">
              {matches.map((supplier) => (
                <li key={supplier}>
                  <button
                    type="button"
                    aria-label={`${supplier}，设置规则`}
                    className="flex min-h-12 w-full items-center justify-between gap-4 px-4 py-3 text-left text-sm transition-colors outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                    onClick={() => onSelect(supplier)}
                  >
                    <span className="min-w-0 font-medium break-words">
                      {supplier}
                    </span>
                    <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                      设置规则
                      <ChevronRight className="size-3.5" aria-hidden="true" />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
