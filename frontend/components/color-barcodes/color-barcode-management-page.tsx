"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, Download, History, Loader2, Palette, Pencil, Plus, Search, Trash2 } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import {
  ApiError,
  createColorBarcode,
  deleteColorBarcode,
  exportColorBarcodes,
  listColorBarcodeBrands,
  listManagedColorBarcodes,
  updateColorBarcode,
} from "@/lib/api"
import type {
  ColorBarcodeBrandSummary,
  ColorBarcodeWritePayload,
  ManagedColorBarcodeItem,
} from "@/lib/types"
import { cn } from "@/lib/utils"


const PAGE_SIZE = 50
const EMPTY_DRAFT: ColorBarcodeWritePayload = {
  brand: "",
  color_barcode: "",
  color_name: "",
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return "操作失败，请稍后重试"
}

function formatDateTime(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date)
}

export function ColorBarcodeManagementPage() {
  const { user } = useAuth()
  const canManage = user?.role_code === "super_admin" || ["商品部", "开发部"].includes(user?.department_code ?? "")
  const [brands, setBrands] = useState<ColorBarcodeBrandSummary[]>([])
  const [selectedBrand, setSelectedBrand] = useState("")
  const [items, setItems] = useState<ManagedColorBarcodeItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<ManagedColorBarcodeItem | null>(null)
  const [draft, setDraft] = useState<ColorBarcodeWritePayload>(EMPTY_DRAFT)
  const [isSaving, setIsSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ManagedColorBarcodeItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [message, setMessage] = useState<{ title: string; description: string } | null>(null)
  const loadRequestIdRef = useRef(0)

  const selectedBrandItem = useMemo(
    () => brands.find((brand) => brand.brand === selectedBrand) ?? null,
    [brands, selectedBrand],
  )
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadBrands = useCallback(async () => {
    try {
      const response = await listColorBarcodeBrands()
      setBrands(response.items)
      setSelectedBrand((current) => (
        response.items.some((brand) => brand.brand === current)
          ? current
          : response.items[0]?.brand || ""
      ))
    } catch (error) {
      setBrands([])
      setMessage({ title: "加载失败", description: getErrorMessage(error) })
    }
  }, [])

  const loadItems = useCallback(async () => {
    await Promise.resolve()
    const requestId = ++loadRequestIdRef.current
    if (!selectedBrand) {
      setItems([])
      setTotal(0)
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    try {
      const response = await listManagedColorBarcodes({
        brand: selectedBrand,
        query,
        page,
        pageSize: PAGE_SIZE,
      })
      if (requestId !== loadRequestIdRef.current) return
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE))
      if (response.total > 0 && page > lastPage) {
        setPage(lastPage)
        return
      }
      setItems(response.items)
      setTotal(response.total)
    } catch (error) {
      if (requestId !== loadRequestIdRef.current) return
      setItems([])
      setTotal(0)
      setMessage({ title: "加载失败", description: getErrorMessage(error) })
    } finally {
      if (requestId === loadRequestIdRef.current) setIsLoading(false)
    }
  }, [page, query, selectedBrand])

  useEffect(() => {
    if (canManage) void Promise.resolve().then(loadBrands)
  }, [canManage, loadBrands])

  useEffect(() => {
    if (canManage) void Promise.resolve().then(loadItems)
  }, [canManage, loadItems])

  const selectBrand = (brand: string) => {
    if (brand === selectedBrand) return
    setSelectedBrand(brand)
    setTotal(brands.find((item) => item.brand === brand)?.total ?? 0)
    setPage(1)
    setQueryInput("")
    setQuery("")
  }

  const openCreate = () => {
    setEditingItem(null)
    setDraft({ ...EMPTY_DRAFT, brand: selectedBrand || brands[0]?.brand || "" })
    setEditorOpen(true)
  }

  const openEdit = (item: ManagedColorBarcodeItem) => {
    setEditingItem(item)
    setDraft({
      brand: item.brand,
      color_barcode: item.color_barcode,
      color_name: item.color_name,
    })
    setEditorOpen(true)
  }

  const save = async () => {
    const payload = {
      brand: draft.brand.trim(),
      color_barcode: draft.color_barcode.trim(),
      color_name: draft.color_name.trim(),
    }
    if (!payload.brand || !payload.color_barcode || !payload.color_name) {
      setMessage({ title: "保存失败", description: "请填写品牌、颜色名称和颜色代码" })
      return
    }
    setIsSaving(true)
    try {
      const result = editingItem
        ? await updateColorBarcode(editingItem.id, payload)
        : await createColorBarcode(payload)
      setEditorOpen(false)
      await loadBrands()
      if (payload.brand !== selectedBrand) selectBrand(payload.brand)
      else await loadItems()
      setMessage({ title: editingItem ? "保存成功" : "新增成功", description: result.message })
    } catch (error) {
      setMessage({ title: "保存失败", description: getErrorMessage(error) })
    } finally {
      setIsSaving(false)
    }
  }

  const remove = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      const result = await deleteColorBarcode(deleteTarget.id)
      setDeleteTarget(null)
      await Promise.all([loadBrands(), loadItems()])
      setMessage({ title: "删除成功", description: result.message })
    } catch (error) {
      setMessage({ title: "删除失败", description: getErrorMessage(error) })
    } finally {
      setIsDeleting(false)
    }
  }

  const exportColors = async () => {
    if (!selectedBrand) return
    setIsExporting(true)
    try {
      const blob = await exportColorBarcodes({ brand: selectedBrand, query })
      const link = document.createElement("a")
      link.href = URL.createObjectURL(blob)
      link.download = `颜色管理_${selectedBrandItem?.brand_label || selectedBrand}.xlsx`
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (error) {
      setMessage({ title: "导出失败", description: getErrorMessage(error) })
    } finally {
      setIsExporting(false)
    }
  }

  if (!canManage) {
    return <div className="app-page"><div className="app-content py-12 text-sm text-muted-foreground">暂无访问权限</div></div>
  }

  return (
    <div className="app-page">
      <div className="app-content space-y-4">
        <div className="page-header">
          <h1 className="page-title">颜色管理</h1>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" className="cursor-pointer gap-1.5" onClick={() => void exportColors()} disabled={!selectedBrand || isExporting}>
              {isExporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
              {isExporting ? "导出中" : "导出"}
            </Button>
            <Button type="button" variant="outline" className="cursor-pointer gap-1.5" onClick={() => setOperationLogOpen(true)}>
              <History className="size-4" />
              操作日志
            </Button>
            <Button type="button" className="cursor-pointer gap-1.5" onClick={openCreate} disabled={!selectedBrand}>
              <Plus className="size-4" />
              新增颜色
            </Button>
          </div>
        </div>

        <div className="flex min-h-11 flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-1.5 shadow-xs">
          {brands.map((brand) => (
            <button
              key={brand.brand}
              type="button"
              onClick={() => selectBrand(brand.brand)}
              className={cn(
                "flex h-8 cursor-pointer items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors",
                selectedBrand === brand.brand
                  ? "bg-foreground text-background shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <span>{brand.brand_label}</span>
              <span className={cn(
                "rounded px-1.5 py-0.5 text-[11px] tabular-nums",
                selectedBrand === brand.brand ? "bg-background/15" : "bg-muted",
              )}>{brand.total}</span>
            </button>
          ))}
        </div>

        <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border p-4">
            <form
              className="flex w-full max-w-md items-center gap-2"
              onSubmit={(event) => {
                event.preventDefault()
                setPage(1)
                setQuery(queryInput.trim())
              }}
            >
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索颜色名称或颜色代码" className="pl-9" />
              </div>
              <Button type="submit" className="cursor-pointer">搜索</Button>
            </form>
            <div className="text-sm text-muted-foreground">
              {selectedBrandItem?.brand_label || "品牌"} · 共 {total} 条
            </div>
          </div>

          <div className="relative h-[clamp(420px,64svh,680px)] overflow-auto">
            {isLoading && items.length > 0 && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-card/70 backdrop-blur-[1px]">
                <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground shadow-sm">
                  <Loader2 className="size-4 animate-spin" />
                  加载中
                </div>
              </div>
            )}
            <table className="w-full min-w-[760px] table-fixed text-sm">
              <thead className="sticky top-0 z-10 bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-20 px-4 py-3 font-medium">序号</th>
                  <th className="w-56 px-4 py-3 font-medium">颜色名称</th>
                  <th className="w-48 px-4 py-3 font-medium">颜色代码</th>
                  <th className="w-44 px-4 py-3 font-medium">最后修改时间</th>
                  <th className="sticky right-0 w-28 bg-muted/95 px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && items.length === 0 ? (
                  <tr><td colSpan={5} className="h-64 text-center text-muted-foreground"><Loader2 className="mr-2 inline size-4 animate-spin" />加载中</td></tr>
                ) : items.length ? items.map((item, index) => (
                  <tr key={item.id} className="group border-t border-border hover:bg-muted/25">
                    <td className="px-4 py-3 text-muted-foreground tabular-nums">{(page - 1) * PAGE_SIZE + index + 1}</td>
                    <td className="px-4 py-3 font-medium text-foreground">{item.color_name}</td>
                    <td className="px-4 py-3"><span className="rounded-md bg-muted px-2 py-1 font-mono text-xs">{item.color_barcode}</span></td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(item.updated_at || item.created_at)}</td>
                    <td className="sticky right-0 bg-card px-3 py-2.5 group-hover:bg-muted/25">
                      <div className="flex justify-end gap-1">
                        <Button type="button" variant="ghost" size="icon" className="cursor-pointer" title="编辑颜色" aria-label={`编辑 ${item.color_name}`} onClick={() => openEdit(item)}><Pencil className="size-4" /></Button>
                        <Button type="button" variant="ghost" size="icon" className="cursor-pointer text-muted-foreground hover:text-destructive" title="删除颜色" aria-label={`删除 ${item.color_name}`} onClick={() => setDeleteTarget(item)}><Trash2 className="size-4" /></Button>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={5} className="h-64 text-center text-sm text-muted-foreground"><Palette className="mx-auto mb-3 size-7 opacity-45" />暂无颜色数据</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex min-h-14 items-center justify-between gap-3 border-t border-border px-4 py-2">
            <span className="text-xs text-muted-foreground">第 {total ? (page - 1) * PAGE_SIZE + 1 : 0}-{Math.min(page * PAGE_SIZE, total)} 条</span>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="icon" className="cursor-pointer" disabled={page <= 1 || isLoading} onClick={() => setPage((current) => Math.max(1, current - 1))} aria-label="上一页"><ChevronLeft className="size-4" /></Button>
              <span className="min-w-20 text-center text-xs tabular-nums text-muted-foreground">{page} / {totalPages}</span>
              <Button type="button" variant="outline" size="icon" className="cursor-pointer" disabled={page >= totalPages || isLoading} onClick={() => setPage((current) => Math.min(totalPages, current + 1))} aria-label="下一页"><ChevronRight className="size-4" /></Button>
            </div>
          </div>
        </section>
      </div>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingItem ? "编辑颜色" : "新增颜色"}</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              void save()
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="color-brand">品牌</Label>
              <Select id="color-brand" value={draft.brand} onChange={(event) => setDraft((current) => ({ ...current, brand: event.target.value }))}>
                {brands.map((brand) => <option key={brand.brand} value={brand.brand}>{brand.brand_label}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="color-name">颜色名称</Label>
              <Input id="color-name" value={draft.color_name} onChange={(event) => setDraft((current) => ({ ...current, color_name: event.target.value }))} placeholder="例如：黑色" autoComplete="off" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="color-code">颜色代码</Label>
              <Input id="color-code" value={draft.color_barcode} onChange={(event) => setDraft((current) => ({ ...current, color_barcode: event.target.value }))} placeholder="例如：01" autoComplete="off" />
            </div>
            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" className="cursor-pointer" onClick={() => setEditorOpen(false)}>取消</Button>
              <Button type="submit" className="cursor-pointer" disabled={isSaving}>{isSaving && <Loader2 className="size-4 animate-spin" />}{isSaving ? "保存中" : "保存"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除颜色"
        description={`确定删除 ${deleteTarget?.brand_label || ""} 的“${deleteTarget?.color_name || ""}（${deleteTarget?.color_barcode || ""}）”？删除后，对应商品档案中的颜色名称会保留，颜色代码将被清空。`}
        confirmLabel={isDeleting ? "删除中" : "删除"}
        variant="destructive"
        onConfirm={() => void remove()}
        onCancel={() => setDeleteTarget(null)}
      />
      <OperationLogDialog module="color_barcode" open={operationLogOpen} title="颜色管理操作日志" onOpenChange={setOperationLogOpen} />
      <MessageDialog open={message !== null} title={message?.title || ""} description={message?.description || ""} onClose={() => setMessage(null)} />
    </div>
  )
}
