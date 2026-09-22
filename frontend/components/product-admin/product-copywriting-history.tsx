"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { ChevronRight, History, LoaderCircle, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { getProductCopywritingHistory, type ProductCopywritingHistorySummary } from "@/lib/api"

type HistoryProps = {
  brand: string
  productId: number
  selectedId: number | null
  onSelect: (id: number) => void
}

export function ProductCopywritingHistory({ brand, productId, selectedId, onSelect }: HistoryProps) {
  const [items, setItems] = useState<ProductCopywritingHistorySummary[]>([])
  const [nextId, setNextId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(0)
  const busy = useRef(false)

  const load = useCallback(async (beforeId?: number) => {
    if (busy.current) return
    busy.current = true
    const request = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const page = await getProductCopywritingHistory(brand, productId, beforeId)
      if (request !== requestId.current) return
      setItems((current) => beforeId === undefined ? page.items : [...current, ...page.items.filter((entry) => !current.some((existing) => existing.id === entry.id))])
      setNextId(page.next_before_id)
    } catch (loadError) {
      if (request === requestId.current) setError(loadError instanceof Error ? loadError.message : "历史版本读取失败，请重试")
    } finally {
      if (request === requestId.current) {
        busy.current = false
        setLoading(false)
      }
    }
  }, [brand, productId])

  useEffect(() => {
    const request = ++requestId.current
    busy.current = true
    void getProductCopywritingHistory(brand, productId).then((page) => {
      if (request !== requestId.current) return
      setItems(page.items)
      setNextId(page.next_before_id)
    }).catch((loadError: unknown) => {
      if (request === requestId.current) setError(loadError instanceof Error ? loadError.message : "历史版本读取失败，请重试")
    }).finally(() => {
      if (request === requestId.current) {
        busy.current = false
        setLoading(false)
      }
    })
    return () => { requestId.current += 1; busy.current = false }
  }, [brand, productId])

  return (
    <section aria-label="历史版本列表" className="mb-5 overflow-hidden rounded-xl border border-border bg-muted/20">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold"><History className="h-4 w-4 text-primary" />已保存版本</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">仅保留成功结果；早期仅能找回数据库现存的版本及上一版备份。</p>
        </div>
        <Button type="button" size="sm" variant="ghost" disabled={loading} onClick={() => void load()}><RefreshCw className="h-3.5 w-3.5" />刷新版本</Button>
      </div>
      {error ? <p role="alert" className="px-4 py-3 text-sm text-destructive">{error}</p> : null}
      <div className="max-h-56 overflow-y-auto divide-y divide-border">
        {items.map((version) => (
          <button key={version.id} type="button" aria-pressed={selectedId === version.id} onClick={() => onSelect(version.id)}
            className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${selectedId === version.id ? "bg-primary/10 text-primary" : "hover:bg-muted"}`}>
            <span className="min-w-0">
              <span className="block text-sm font-medium tabular-nums">{new Date(version.generated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</span>
              <span className="mt-1 block break-all text-xs text-muted-foreground">{version.sku} · {version.model || "模型未记录"}</span>
            </span>
            <span className="flex shrink-0 items-center gap-1 text-xs">{selectedId === version.id ? "正在查看" : "查看版本"}<ChevronRight className="h-3.5 w-3.5" /></span>
          </button>
        ))}
      </div>
      {loading ? <p role="status" className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" />正在读取历史版本…</p> : null}
      {!loading && !error && items.length === 0 ? <p className="px-4 py-5 text-sm text-muted-foreground">暂无可查看的历史版本。</p> : null}
      {nextId !== null ? <div className="border-t border-border px-4 py-2"><Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void load(nextId)}>加载更早版本</Button></div> : null}
    </section>
  )
}
