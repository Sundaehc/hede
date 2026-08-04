"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronRight, Edit, History, Plus, Search, Trash2, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import {
  ApiError,
  createWarehouse,
  createWarehouseBrand,
  deleteWarehouse,
  deleteWarehouseBrand,
  listWarehouseBrands,
  listWarehouses,
  updateWarehouse,
  updateWarehouseBrand,
  type WarehouseBrandItem,
  type WarehouseItem,
} from "@/lib/api"

type WarehouseForm = {
  brand: string
  name: string
  address: string
  notes: string
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function WarehousesPage() {
  const [brands, setBrands] = useState<WarehouseBrandItem[]>([])
  const [warehouses, setWarehouses] = useState<WarehouseItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null)

  const [brandFormOpen, setBrandFormOpen] = useState(false)
  const [brandFormMode, setBrandFormMode] = useState<"create" | "edit">("create")
  const [brandName, setBrandName] = useState("")
  const [editingBrandId, setEditingBrandId] = useState<number | null>(null)
  const [isSavingBrand, setIsSavingBrand] = useState(false)
  const [deleteBrandTarget, setDeleteBrandTarget] = useState<WarehouseBrandItem | null>(null)
  const [isDeletingBrand, setIsDeletingBrand] = useState(false)

  const [warehouseFormOpen, setWarehouseFormOpen] = useState(false)
  const [warehouseFormMode, setWarehouseFormMode] = useState<"create" | "edit">("create")
  const [warehouseForm, setWarehouseForm] = useState<WarehouseForm>({ brand: "", name: "", address: "", notes: "" })
  const [editingWarehouseId, setEditingWarehouseId] = useState<number | null>(null)
  const [isSavingWarehouse, setIsSavingWarehouse] = useState(false)
  const [deleteWarehouseTarget, setDeleteWarehouseTarget] = useState<WarehouseItem | null>(null)
  const [isDeletingWarehouse, setIsDeletingWarehouse] = useState(false)

  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const [brandResponse, warehouseResponse] = await Promise.all([listWarehouseBrands(), listWarehouses()])
      setBrands(brandResponse.items)
      setWarehouses(warehouseResponse.items)
    } catch (error) {
      setBrands([])
      setWarehouses([])
      setMessageContent({ title: "加载失败", description: getErrorMessage(error) })
      setMessageOpen(true)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filteredBrands = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return brands
    return brands.filter((brand) => [brand.name, ...warehouses.filter((warehouse) => warehouse.brand === brand.name).map((warehouse) => warehouse.name)]
      .some((value) => value.toLowerCase().includes(term)))
  }, [brands, query, warehouses])

  const activeBrand = useMemo(() => {
    if (filteredBrands.length === 0) return null
    return filteredBrands.find((brand) => brand.id === selectedBrandId) ?? filteredBrands[0]
  }, [filteredBrands, selectedBrandId])

  useEffect(() => {
    if (filteredBrands.length === 0) {
      if (selectedBrandId !== null) setSelectedBrandId(null)
      return
    }
    if (!selectedBrandId || !filteredBrands.some((brand) => brand.id === selectedBrandId)) {
      setSelectedBrandId(filteredBrands[0].id)
    }
  }, [filteredBrands, selectedBrandId])

  const visibleWarehouses = useMemo(() => (
    activeBrand ? warehouses.filter((warehouse) => warehouse.brand === activeBrand.name) : []
  ), [activeBrand, warehouses])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreateBrand = () => {
    setBrandFormMode("create")
    setBrandName("")
    setEditingBrandId(null)
    setBrandFormOpen(true)
  }

  const openEditBrand = (brand: WarehouseBrandItem) => {
    setBrandFormMode("edit")
    setBrandName(brand.name)
    setEditingBrandId(brand.id)
    setBrandFormOpen(true)
  }

  const openCreateWarehouse = () => {
    if (!activeBrand) return
    setWarehouseFormMode("create")
    setWarehouseForm({ brand: activeBrand.name, name: "", address: "", notes: "" })
    setEditingWarehouseId(null)
    setWarehouseFormOpen(true)
  }

  const openEditWarehouse = (warehouse: WarehouseItem) => {
    setWarehouseFormMode("edit")
    setWarehouseForm({
      brand: warehouse.brand || activeBrand?.name || "通用",
      name: warehouse.name,
      address: warehouse.address || "",
      notes: warehouse.notes || "",
    })
    setEditingWarehouseId(warehouse.id)
    setWarehouseFormOpen(true)
  }

  const handleSaveBrand = async () => {
    const name = brandName.trim()
    if (!name) return showMessage("保存失败", "品牌名称不能为空")
    setIsSavingBrand(true)
    try {
      const result = brandFormMode === "create"
        ? await createWarehouseBrand({ name })
        : editingBrandId !== null
          ? await updateWarehouseBrand(editingBrandId, { name })
          : null
      if (result) setSelectedBrandId(result.item.id)
      setBrandFormOpen(false)
      await load()
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSavingBrand(false)
    }
  }

  const handleSaveWarehouse = async () => {
    const name = warehouseForm.name.trim()
    const brand = warehouseForm.brand.trim()
    if (!brand) return showMessage("保存失败", "请先选择所属品牌")
    if (!name) return showMessage("保存失败", "仓库名称不能为空")
    setIsSavingWarehouse(true)
    try {
      const payload = { ...warehouseForm, brand, name }
      if (warehouseFormMode === "create") {
        await createWarehouse(payload)
      } else if (editingWarehouseId !== null) {
        await updateWarehouse(editingWarehouseId, payload)
      }
      setWarehouseFormOpen(false)
      await load()
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSavingWarehouse(false)
    }
  }

  const handleDeleteBrand = async () => {
    if (!deleteBrandTarget) return
    setIsDeletingBrand(true)
    try {
      await deleteWarehouseBrand(deleteBrandTarget.id)
      setDeleteBrandTarget(null)
      await load()
    } catch (error) {
      showMessage("删除失败", getErrorMessage(error))
    } finally {
      setIsDeletingBrand(false)
    }
  }

  const handleDeleteWarehouse = async () => {
    if (!deleteWarehouseTarget) return
    setIsDeletingWarehouse(true)
    try {
      await deleteWarehouse(deleteWarehouseTarget.id)
      setDeleteWarehouseTarget(null)
      await load()
    } catch (error) {
      showMessage("删除失败", getErrorMessage(error))
    } finally {
      setIsDeletingWarehouse(false)
    }
  }

  return (
    <div className="app-page">
      <div className="app-content">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <h1 className="page-title">仓库管理</h1>
            <span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">{warehouses.length} 个仓库</span>
          </div>
          <Button size="sm" variant="outline" onClick={() => setOperationLogOpen(true)} className="cursor-pointer">
            <History className="h-4 w-4" />
            <span className="ml-1.5">操作日志</span>
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <section className="surface-panel p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-foreground">品牌</p>
              <Button size="sm" onClick={openCreateBrand} className="cursor-pointer">
                <Plus className="h-4 w-4" />
                <span className="ml-1.5">新增品牌</span>
              </Button>
            </div>
            <form className="mt-3 flex gap-2" onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()) }}>
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索品牌或仓库" className="pl-9" />
              </div>
              {(query || queryInput) && <Button type="button" size="icon" variant="outline" className="cursor-pointer" aria-label="清空搜索" onClick={() => { setQuery(""); setQueryInput("") }}><X className="h-4 w-4" /></Button>}
            </form>
            <div className="mt-3 space-y-1.5">
              {isLoading && <div className="rounded-xl border border-border bg-card px-3 py-10 text-center text-sm text-muted-foreground">加载中...</div>}
              {!isLoading && filteredBrands.length === 0 && <div className="rounded-xl border border-border bg-card px-3 py-10 text-center text-sm text-muted-foreground">{query ? "暂无匹配品牌" : "暂无品牌数据"}</div>}
              {!isLoading && filteredBrands.map((brand) => {
                const selected = brand.id === activeBrand?.id
                return (
                  <div key={brand.id} className={`group relative flex items-center gap-1 overflow-hidden rounded-xl border px-2 py-2 shadow-xs transition-all duration-150 ${selected ? "border-foreground bg-muted/70 shadow-sm ring-1 ring-foreground/10" : "border-border bg-card hover:-translate-y-px hover:border-foreground/25 hover:bg-muted/45 hover:shadow-sm"}`}>
                    <span aria-hidden="true" className={`absolute inset-y-2 left-0 w-1 rounded-r-full bg-foreground ${selected ? "opacity-100" : "opacity-0 group-hover:opacity-25"}`} />
                    <button type="button" aria-pressed={selected} onClick={() => setSelectedBrandId(brand.id)} className="relative flex min-h-8 min-w-0 flex-1 cursor-pointer items-center justify-between gap-2 rounded-lg px-1.5 text-left text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/35">
                      <span className="truncate font-medium text-foreground">{brand.name}</span>
                      <span className={`flex shrink-0 items-center gap-1.5 rounded-full px-1.5 py-0.5 text-xs ${selected ? "bg-background text-foreground shadow-xs" : "text-muted-foreground"}`}>
                        <span>{brand.warehouse_count} 个</span>
                        <ChevronRight className="h-4 w-4" />
                      </span>
                    </button>
                    <Button variant="ghost" size="icon" onClick={() => openEditBrand(brand)} className="relative h-8 w-8 cursor-pointer" aria-label={`编辑品牌 ${brand.name}`}><Edit className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteBrandTarget(brand)} className="relative h-8 w-8 cursor-pointer" aria-label={`删除品牌 ${brand.name}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                  </div>
                )
              })}
            </div>
          </section>

          <section className="surface-panel p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground">{activeBrand?.name || "请选择品牌"}</p>
                  {activeBrand && <span className="rounded-full border border-border bg-muted/45 px-2.5 py-0.5 text-xs text-muted-foreground tabular-nums">{visibleWarehouses.length} 个仓库</span>}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">选择品牌后维护其下仓库</p>
              </div>
              <Button size="sm" onClick={openCreateWarehouse} disabled={!activeBrand} className="cursor-pointer"><Plus className="h-4 w-4" /><span className="ml-1.5">新增仓库</span></Button>
            </div>
            <div className="mt-3 table-panel overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="table-head-row"><th className="px-4 py-3 font-medium">仓库名称</th><th className="px-4 py-3 font-medium">地址</th><th className="px-4 py-3 font-medium">备注</th><th className="w-24 px-4 py-3 font-medium">操作</th></tr></thead>
                  <tbody className="divide-y divide-border">
                    {isLoading && <tr><td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">加载中...</td></tr>}
                    {!isLoading && !activeBrand && <tr><td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">请先新增或选择品牌</td></tr>}
                    {!isLoading && activeBrand && visibleWarehouses.length === 0 && <tr><td colSpan={4} className="px-4 py-12 text-center text-muted-foreground">该品牌暂无仓库</td></tr>}
                    {!isLoading && visibleWarehouses.map((warehouse) => <tr key={warehouse.id} className="table-row"><td className="px-4 py-2.5 font-medium">{warehouse.name}</td><td className="px-4 py-2.5">{warehouse.address || "-"}</td><td className="max-w-64 truncate px-4 py-2.5" title={warehouse.notes || ""}>{warehouse.notes || "-"}</td><td className="px-4 py-2.5"><div className="flex items-center gap-0.5"><Button variant="ghost" size="icon" onClick={() => openEditWarehouse(warehouse)} className="cursor-pointer" aria-label={`编辑仓库 ${warehouse.name}`}><Edit className="h-4 w-4" /></Button><Button variant="ghost" size="icon" onClick={() => setDeleteWarehouseTarget(warehouse)} className="cursor-pointer" aria-label={`删除仓库 ${warehouse.name}`}><Trash2 className="h-4 w-4 text-destructive" /></Button></div></td></tr>)}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      </div>

      <Dialog open={brandFormOpen} onOpenChange={setBrandFormOpen}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>{brandFormMode === "create" ? "新增品牌" : "编辑品牌"}</DialogTitle></DialogHeader><div className="space-y-1.5 py-2"><Label htmlFor="warehouse-brand-name">品牌 *</Label><Input id="warehouse-brand-name" value={brandName} onChange={(event) => setBrandName(event.target.value)} placeholder="例如：千百度" /></div><DialogFooter><Button variant="outline" onClick={() => setBrandFormOpen(false)} disabled={isSavingBrand} className="cursor-pointer">取消</Button><Button onClick={handleSaveBrand} disabled={isSavingBrand} className="cursor-pointer">{isSavingBrand ? "保存中..." : "保存"}</Button></DialogFooter></DialogContent></Dialog>
      <Dialog open={warehouseFormOpen} onOpenChange={setWarehouseFormOpen}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>{warehouseFormMode === "create" ? "新增仓库" : "编辑仓库"}</DialogTitle></DialogHeader><div className="space-y-4 py-2"><div className="space-y-1.5"><Label htmlFor="warehouse-brand">所属品牌 *</Label><Input id="warehouse-brand" value={warehouseForm.brand} disabled /></div><div className="space-y-1.5"><Label htmlFor="warehouse-name">仓库名称 *</Label><Input id="warehouse-name" value={warehouseForm.name} onChange={(event) => setWarehouseForm((current) => ({ ...current, name: event.target.value }))} placeholder="仓库名称" /></div><div className="space-y-1.5"><Label htmlFor="warehouse-address">地址</Label><Input id="warehouse-address" value={warehouseForm.address} onChange={(event) => setWarehouseForm((current) => ({ ...current, address: event.target.value }))} placeholder="仓库地址" /></div><div className="space-y-1.5"><Label htmlFor="warehouse-notes">备注</Label><Input id="warehouse-notes" value={warehouseForm.notes} onChange={(event) => setWarehouseForm((current) => ({ ...current, notes: event.target.value }))} placeholder="备注" /></div></div><DialogFooter><Button variant="outline" onClick={() => setWarehouseFormOpen(false)} disabled={isSavingWarehouse} className="cursor-pointer">取消</Button><Button onClick={handleSaveWarehouse} disabled={isSavingWarehouse} className="cursor-pointer">{isSavingWarehouse ? "保存中..." : "保存"}</Button></DialogFooter></DialogContent></Dialog>

      <ConfirmDialog open={deleteBrandTarget !== null} title="确认删除" description={`确定删除品牌 ${deleteBrandTarget?.name}？该品牌下的仓库需要先调整或删除。`} confirmLabel={isDeletingBrand ? "删除中..." : "删除"} variant="destructive" onConfirm={handleDeleteBrand} onCancel={() => setDeleteBrandTarget(null)} />
      <ConfirmDialog open={deleteWarehouseTarget !== null} title="确认删除" description={`确定删除仓库 ${deleteWarehouseTarget?.name}？此操作不可撤销。`} confirmLabel={isDeletingWarehouse ? "删除中..." : "删除"} variant="destructive" onConfirm={handleDeleteWarehouse} onCancel={() => setDeleteWarehouseTarget(null)} />
      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />
      <OperationLogDialog module="warehouse" title="仓库管理操作日志" open={operationLogOpen} onOpenChange={setOperationLogOpen} />
    </div>
  )
}
