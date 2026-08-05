"use client"

import { type DragEvent, useCallback, useEffect, useMemo, useState } from "react"
import { ChevronRight, Edit, GripVertical, History, Plus, Search, Trash2, X } from "lucide-react"

import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  ApiError,
  createGeneralCustomerBrand,
  createGeneralCustomerShop,
  createGeneralCustomerUnit,
  deleteGeneralCustomerBrand,
  deleteGeneralCustomerShop,
  deleteGeneralCustomerUnit,
  listGeneralCustomerBrands,
  listGeneralCustomerShops,
  listGeneralCustomerUnits,
  reorderGeneralCustomerBrands,
  reorderGeneralCustomerShops,
  reorderGeneralCustomerUnits,
  updateGeneralCustomerBrand,
  updateGeneralCustomerShop,
  updateGeneralCustomerUnit,
} from "@/lib/api"
import type {
  GeneralCustomerBrandItem,
  GeneralCustomerShopItem,
  GeneralCustomerUnitItem,
} from "@/lib/types"

type GeneralCustomerShopsTabProps = { standalone?: boolean }
type DropPlacement = "before" | "after"
type DropTarget = { id: number; placement: DropPlacement }

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

function dropPlacement(event: DragEvent<HTMLElement>): DropPlacement {
  const bounds = event.currentTarget.getBoundingClientRect()
  return event.clientY < bounds.top + bounds.height / 2 ? "before" : "after"
}

function moveById<T extends { id: number }>(items: T[], sourceId: number, targetId: number, placement: DropPlacement) {
  const sourceIndex = items.findIndex((item) => item.id === sourceId)
  if (sourceIndex < 0 || sourceId === targetId) return items
  const next = [...items]
  const [source] = next.splice(sourceIndex, 1)
  const targetIndex = next.findIndex((item) => item.id === targetId)
  if (targetIndex < 0) return items
  next.splice(placement === "after" ? targetIndex + 1 : targetIndex, 0, source)
  return next
}

export function GeneralCustomerShopsTab({ standalone = false }: GeneralCustomerShopsTabProps) {
  const [brands, setBrands] = useState<GeneralCustomerBrandItem[]>([])
  const [shops, setShops] = useState<GeneralCustomerShopItem[]>([])
  const [units, setUnits] = useState<GeneralCustomerUnitItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null)

  const [brandFormOpen, setBrandFormOpen] = useState(false)
  const [brandFormMode, setBrandFormMode] = useState<"create" | "edit">("create")
  const [brandName, setBrandName] = useState("")
  const [editingBrandId, setEditingBrandId] = useState<number | null>(null)
  const [isSavingBrand, setIsSavingBrand] = useState(false)
  const [deleteBrandTarget, setDeleteBrandTarget] = useState<GeneralCustomerBrandItem | null>(null)
  const [isDeletingBrand, setIsDeletingBrand] = useState(false)

  const [shopFormOpen, setShopFormOpen] = useState(false)
  const [shopFormMode, setShopFormMode] = useState<"create" | "edit">("create")
  const [shopForm, setShopForm] = useState({ customer_name: "", shop_name: "" })
  const [editingShopId, setEditingShopId] = useState<number | null>(null)
  const [isSavingShop, setIsSavingShop] = useState(false)
  const [deleteShopTarget, setDeleteShopTarget] = useState<GeneralCustomerShopItem | null>(null)
  const [isDeletingShop, setIsDeletingShop] = useState(false)

  const [unitFormOpen, setUnitFormOpen] = useState(false)
  const [unitFormMode, setUnitFormMode] = useState<"create" | "edit">("create")
  const [unitForm, setUnitForm] = useState({ shop_id: 0, unit_name: "" })
  const [editingUnitId, setEditingUnitId] = useState<number | null>(null)
  const [isSavingUnit, setIsSavingUnit] = useState(false)
  const [deleteUnitTarget, setDeleteUnitTarget] = useState<GeneralCustomerUnitItem | null>(null)
  const [isDeletingUnit, setIsDeletingUnit] = useState(false)
  const [draggedBrandId, setDraggedBrandId] = useState<number | null>(null)
  const [draggedShopId, setDraggedShopId] = useState<number | null>(null)
  const [draggedUnitId, setDraggedUnitId] = useState<number | null>(null)
  const [brandDropTarget, setBrandDropTarget] = useState<DropTarget | null>(null)
  const [shopDropTarget, setShopDropTarget] = useState<DropTarget | null>(null)
  const [unitDropTarget, setUnitDropTarget] = useState<DropTarget | null>(null)
  const [isReordering, setIsReordering] = useState(false)

  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const [brandResponse, shopResponse, unitResponse] = await Promise.all([
        listGeneralCustomerBrands(),
        listGeneralCustomerShops(),
        listGeneralCustomerUnits(),
      ])
      setBrands(brandResponse.items)
      setShops(shopResponse.items)
      setUnits(unitResponse.items)
    } catch (error) {
      setBrands([])
      setShops([])
      setUnits([])
      setMessageContent({ title: "加载失败", description: getErrorMessage(error) })
      setMessageOpen(true)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const filteredBrands = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return brands
    return brands.filter((brand) => {
      const brandShops = shops.filter((shop) => shop.customer_name === brand.name)
      const brandUnits = brandShops.flatMap((shop) => units.filter((unit) => unit.shop_id === shop.id))
      return [brand.name, ...brandShops.map((shop) => shop.shop_name), ...brandUnits.map((unit) => unit.unit_name)]
        .some((value) => value.toLowerCase().includes(term))
    })
  }, [brands, query, shops, units])
  const activeBrand = useMemo(() => (
    filteredBrands.find((brand) => brand.id === selectedBrandId) ?? filteredBrands[0] ?? null
  ), [filteredBrands, selectedBrandId])
  const visibleShops = useMemo(() => (
    activeBrand ? shops.filter((shop) => shop.customer_name === activeBrand.name) : []
  ), [activeBrand, shops])

  useEffect(() => {
    if (activeBrand && activeBrand.id !== selectedBrandId) setSelectedBrandId(activeBrand.id)
    if (!activeBrand && selectedBrandId !== null) setSelectedBrandId(null)
  }, [activeBrand, selectedBrandId])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }
  const save = async (action: () => Promise<void>, setSaving: (value: boolean) => void, close: () => void) => {
    setSaving(true)
    try { await action(); close(); await load() } catch (error) { showMessage("保存失败", getErrorMessage(error)) } finally { setSaving(false) }
  }
  const openBrand = (item?: GeneralCustomerBrandItem) => {
    setBrandFormMode(item ? "edit" : "create")
    setBrandName(item?.name || "")
    setEditingBrandId(item?.id ?? null)
    setBrandFormOpen(true)
  }
  const openShop = (item?: GeneralCustomerShopItem) => {
    setShopFormMode(item ? "edit" : "create")
    setShopForm({ customer_name: item?.customer_name || activeBrand?.name || "", shop_name: item?.shop_name || "" })
    setEditingShopId(item?.id ?? null)
    setShopFormOpen(true)
  }
  const openUnit = (shop: GeneralCustomerShopItem, item?: GeneralCustomerUnitItem) => {
    setUnitFormMode(item ? "edit" : "create")
    setUnitForm({ shop_id: item?.shop_id || shop.id, unit_name: item?.unit_name || "" })
    setEditingUnitId(item?.id ?? null)
    setUnitFormOpen(true)
  }

  const handleBrandDrop = async (targetId: number, placement: DropPlacement) => {
    if (isReordering || draggedBrandId === null || draggedBrandId === targetId) return
    const nextBrands = moveById(brands, draggedBrandId, targetId, placement)
    setDraggedBrandId(null)
    setBrandDropTarget(null)
    if (nextBrands === brands) return
    setBrands(nextBrands)
    setIsReordering(true)
    try {
      await reorderGeneralCustomerBrands(nextBrands.map((brand) => brand.id))
    } catch (error) {
      setBrands(brands)
      showMessage("排序保存失败", getErrorMessage(error))
    } finally {
      setIsReordering(false)
    }
  }

  const handleShopDrop = async (targetId: number, placement: DropPlacement) => {
    if (isReordering || !activeBrand || draggedShopId === null || draggedShopId === targetId) return
    const nextGroup = moveById(visibleShops, draggedShopId, targetId, placement)
    setDraggedShopId(null)
    setShopDropTarget(null)
    if (nextGroup === visibleShops) return
    const groupIds = new Set(nextGroup.map((shop) => shop.id))
    let groupIndex = 0
    const nextShops = shops.map((shop) => (groupIds.has(shop.id) ? nextGroup[groupIndex++] : shop))
    setShops(nextShops)
    setIsReordering(true)
    try {
      await reorderGeneralCustomerShops(activeBrand.name, nextGroup.map((shop) => shop.id))
    } catch (error) {
      setShops(shops)
      showMessage("排序保存失败", getErrorMessage(error))
    } finally {
      setIsReordering(false)
    }
  }

  const handleUnitDrop = async (shop: GeneralCustomerShopItem, targetId: number, placement: DropPlacement) => {
    if (isReordering || draggedUnitId === null || draggedUnitId === targetId) return
    const shopUnits = units.filter((unit) => unit.shop_id === shop.id)
    const nextGroup = moveById(shopUnits, draggedUnitId, targetId, placement)
    setDraggedUnitId(null)
    setUnitDropTarget(null)
    if (nextGroup === shopUnits) return
    const groupIds = new Set(nextGroup.map((unit) => unit.id))
    let groupIndex = 0
    const nextUnits = units.map((unit) => (groupIds.has(unit.id) ? nextGroup[groupIndex++] : unit))
    setUnits(nextUnits)
    setIsReordering(true)
    try {
      await reorderGeneralCustomerUnits(shop.id, nextGroup.map((unit) => unit.id))
    } catch (error) {
      setUnits(units)
      showMessage("排序保存失败", getErrorMessage(error))
    } finally {
      setIsReordering(false)
    }
  }

  return (
    <div className={standalone ? "app-page" : "surface-panel p-4"}>
      <div className={standalone ? "app-content" : ""}>
        <div className={standalone ? "page-header" : "mb-4 flex items-center justify-between gap-3"}>
          <div className="flex items-center gap-3"><h1 className={standalone ? "page-title" : "text-sm font-medium text-foreground"}>一般客户</h1><span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">{units.length} 个单位</span></div>
          <Button size="sm" variant="outline" onClick={() => setOperationLogOpen(true)} className="cursor-pointer"><History className="h-4 w-4" /><span className="ml-1.5">操作日志</span></Button>
        </div>
        <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
          <section className="surface-panel p-4">
            <div className="flex items-center justify-between gap-2"><p className="text-sm font-medium">品牌</p><Button size="sm" onClick={() => openBrand()} className="cursor-pointer"><Plus className="h-4 w-4" /><span className="ml-1">新增</span></Button></div>
            <form className="mt-3 flex gap-2" onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()) }}><div className="relative min-w-0 flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索品牌、店铺或单位" className="pl-9" /></div>{(query || queryInput) && <Button type="button" variant="outline" size="icon" className="cursor-pointer" onClick={() => { setQuery(""); setQueryInput("") }}><X className="h-4 w-4" /></Button>}</form>
            <div className="mt-3 space-y-1.5">
              {isLoading && <div className="py-10 text-center text-sm text-muted-foreground">加载中...</div>}
              {!isLoading && filteredBrands.length === 0 && <div className="py-10 text-center text-sm text-muted-foreground">暂无品牌</div>}
              {filteredBrands.map((brand) => (
                <div key={brand.id} onDragOver={(event) => { if (draggedBrandId === null || draggedBrandId === brand.id) return; event.preventDefault(); const nextTarget = { id: brand.id, placement: dropPlacement(event) }; setBrandDropTarget((current) => current?.id === nextTarget.id && current.placement === nextTarget.placement ? current : nextTarget) }} onDrop={(event) => { event.preventDefault(); void handleBrandDrop(brand.id, brandDropTarget?.id === brand.id ? brandDropTarget.placement : "before") }} className={`group relative flex items-center gap-1 overflow-hidden rounded-xl border p-2 transition-all duration-150 ${brand.id === activeBrand?.id ? "border-foreground bg-muted/70" : "border-border bg-card"} ${draggedBrandId === brand.id ? "scale-[0.98] opacity-45" : ""} ${brandDropTarget?.id === brand.id && draggedBrandId !== brand.id ? brandDropTarget.placement === "before" ? "translate-y-2" : "-translate-y-2" : ""}`}>
                  {brandDropTarget?.id === brand.id && draggedBrandId !== brand.id && <span aria-hidden="true" className={`pointer-events-none absolute inset-x-2 z-10 h-0.5 rounded-full bg-primary shadow-sm ${brandDropTarget.placement === "before" ? "top-0" : "bottom-0"}`} />}
                  <button type="button" draggable={!isReordering} onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; setBrandDropTarget(null); setDraggedBrandId(brand.id) }} onDragEnd={() => { setDraggedBrandId(null); setBrandDropTarget(null) }} className="flex size-8 shrink-0 cursor-grab items-center justify-center rounded-md text-muted-foreground hover:bg-muted active:cursor-grabbing" aria-label={`拖拽排序品牌 ${brand.name}`} title="拖拽排序"><GripVertical className="h-4 w-4" /></button>
                  <button type="button" onClick={() => setSelectedBrandId(brand.id)} className="flex min-w-0 flex-1 cursor-pointer items-center justify-between gap-2 text-left text-sm"><span className="truncate font-medium">{brand.name}</span><span className="flex items-center gap-1 text-xs text-muted-foreground">{brand.shop_count}<ChevronRight className="h-4 w-4" /></span></button>
                  <Button size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => openBrand(brand)}><Edit className="h-4 w-4" /></Button><Button size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => setDeleteBrandTarget(brand)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                </div>
              ))}
            </div>
          </section>
          <section className="surface-panel p-4">
            <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium">{activeBrand?.name || "店铺与单位"}</p><p className="mt-1 text-xs text-muted-foreground">店铺下可维护实际往来单位</p></div><Button size="sm" disabled={!activeBrand} onClick={() => openShop()} className="cursor-pointer"><Plus className="h-4 w-4" /><span className="ml-1.5">新增店铺</span></Button></div>
            <div className="mt-3 space-y-3">
              {!isLoading && !activeBrand && <div className="py-10 text-center text-sm text-muted-foreground">请选择品牌</div>}
              {!isLoading && activeBrand && visibleShops.length === 0 && <div className="py-10 text-center text-sm text-muted-foreground">该品牌暂无店铺</div>}
              {visibleShops.map((shop) => {
                const shopUnits = units.filter((unit) => unit.shop_id === shop.id)
                return (
                  <div key={shop.id} onDragOver={(event) => { if (draggedShopId === null || draggedShopId === shop.id) return; event.preventDefault(); const nextTarget = { id: shop.id, placement: dropPlacement(event) }; setShopDropTarget((current) => current?.id === nextTarget.id && current.placement === nextTarget.placement ? current : nextTarget) }} onDrop={(event) => { event.preventDefault(); void handleShopDrop(shop.id, shopDropTarget?.id === shop.id ? shopDropTarget.placement : "before") }} className={`relative overflow-hidden rounded-lg border bg-card transition-all duration-150 ${draggedShopId === shop.id ? "scale-[0.99] opacity-45" : "border-border"} ${shopDropTarget?.id === shop.id && draggedShopId !== shop.id ? shopDropTarget.placement === "before" ? "translate-y-2 border-t-2 border-t-primary" : "-translate-y-2 border-b-2 border-b-primary" : ""}`}>
                    {shopDropTarget?.id === shop.id && draggedShopId !== shop.id && <span aria-hidden="true" className={`pointer-events-none absolute inset-x-2 z-10 h-0.5 rounded-full bg-primary shadow-sm ${shopDropTarget.placement === "before" ? "top-0" : "bottom-0"}`} />}
                    <div className="flex items-center gap-2 border-b border-border px-3 py-2.5"><button type="button" draggable={!isReordering} onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; setShopDropTarget(null); setDraggedShopId(shop.id) }} onDragEnd={() => { setDraggedShopId(null); setShopDropTarget(null) }} className="flex size-8 shrink-0 cursor-grab items-center justify-center rounded-md text-muted-foreground hover:bg-muted active:cursor-grabbing" aria-label={`拖拽排序店铺 ${shop.shop_name}`} title="拖拽排序"><GripVertical className="h-4 w-4" /></button><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{shop.shop_name}</p><p className="mt-0.5 text-xs text-muted-foreground">{shopUnits.length} 个单位</p></div><Button size="sm" variant="outline" onClick={() => openUnit(shop)} className="cursor-pointer"><Plus className="h-3.5 w-3.5" /><span className="ml-1">新增单位</span></Button><Button size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => openShop(shop)}><Edit className="h-4 w-4" /></Button><Button size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => setDeleteShopTarget(shop)}><Trash2 className="h-4 w-4 text-destructive" /></Button></div>
                    <div className="divide-y divide-border">{shopUnits.length === 0 ? <p className="px-3 py-4 text-sm text-muted-foreground">暂无单位</p> : shopUnits.map((unit) => <div key={unit.id} onDragOver={(event) => { if (draggedUnitId === null || draggedUnitId === unit.id) return; event.preventDefault(); const nextTarget = { id: unit.id, placement: dropPlacement(event) }; setUnitDropTarget((current) => current?.id === nextTarget.id && current.placement === nextTarget.placement ? current : nextTarget) }} onDrop={(event) => { event.preventDefault(); void handleUnitDrop(shop, unit.id, unitDropTarget?.id === unit.id ? unitDropTarget.placement : "before") }} className={`relative flex items-center gap-2 px-3 py-2 transition-all duration-150 ${draggedUnitId === unit.id ? "scale-[0.99] opacity-40" : ""} ${unitDropTarget?.id === unit.id && draggedUnitId !== unit.id ? unitDropTarget.placement === "before" ? "translate-y-2 bg-primary/5" : "-translate-y-2 bg-primary/5" : ""}`}>{unitDropTarget?.id === unit.id && draggedUnitId !== unit.id && <span aria-hidden="true" className={`pointer-events-none absolute inset-x-2 z-10 h-0.5 rounded-full bg-primary shadow-sm ${unitDropTarget.placement === "before" ? "top-0" : "bottom-0"}`} />}<button type="button" draggable={!isReordering} onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; setUnitDropTarget(null); setDraggedUnitId(unit.id) }} onDragEnd={() => { setDraggedUnitId(null); setUnitDropTarget(null) }} className="flex size-8 shrink-0 cursor-grab items-center justify-center rounded-md text-muted-foreground hover:bg-muted active:cursor-grabbing" aria-label={`拖拽排序单位 ${unit.unit_name}`} title="拖拽排序"><GripVertical className="h-4 w-4" /></button><span className="min-w-0 flex-1 truncate text-sm">{unit.unit_name}</span><Button size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => openUnit(shop, unit)}><Edit className="h-4 w-4" /></Button><Button size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => setDeleteUnitTarget(unit)}><Trash2 className="h-4 w-4 text-destructive" /></Button></div>)}</div>
                  </div>
                )
              })}
            </div>
          </section>
        </div>
      </div>

      <Dialog open={brandFormOpen} onOpenChange={setBrandFormOpen}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>{brandFormMode === "create" ? "新增品牌" : "编辑品牌"}</DialogTitle></DialogHeader><div className="space-y-1.5 py-2"><Label>品牌名称 *</Label><Input value={brandName} onChange={(event) => setBrandName(event.target.value)} /></div><DialogFooter><Button variant="outline" className="cursor-pointer" onClick={() => setBrandFormOpen(false)} disabled={isSavingBrand}>取消</Button><Button className="cursor-pointer" disabled={isSavingBrand} onClick={() => { const name = brandName.trim(); if (!name) return showMessage("保存失败", "品牌名称不能为空"); void save(async () => { if (brandFormMode === "create") await createGeneralCustomerBrand({ name }); else if (editingBrandId !== null) await updateGeneralCustomerBrand(editingBrandId, { name }) }, setIsSavingBrand, () => setBrandFormOpen(false)) }}>{isSavingBrand ? "保存中..." : "保存"}</Button></DialogFooter></DialogContent></Dialog>
      <Dialog open={shopFormOpen} onOpenChange={setShopFormOpen}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>{shopFormMode === "create" ? "新增店铺" : "编辑店铺"}</DialogTitle></DialogHeader><div className="space-y-4 py-2"><div className="space-y-1.5"><Label>所属品牌 *</Label><Input value={shopForm.customer_name} disabled /></div><div className="space-y-1.5"><Label>店铺名称 *</Label><Input value={shopForm.shop_name} onChange={(event) => setShopForm((current) => ({ ...current, shop_name: event.target.value }))} /></div></div><DialogFooter><Button variant="outline" className="cursor-pointer" onClick={() => setShopFormOpen(false)} disabled={isSavingShop}>取消</Button><Button className="cursor-pointer" disabled={isSavingShop} onClick={() => { const shop_name = shopForm.shop_name.trim(); if (!shop_name) return showMessage("保存失败", "店铺名称不能为空"); void save(async () => { const payload = { ...shopForm, shop_name }; if (shopFormMode === "create") await createGeneralCustomerShop(payload); else if (editingShopId !== null) await updateGeneralCustomerShop(editingShopId, payload) }, setIsSavingShop, () => setShopFormOpen(false)) }}>{isSavingShop ? "保存中..." : "保存"}</Button></DialogFooter></DialogContent></Dialog>
      <Dialog open={unitFormOpen} onOpenChange={setUnitFormOpen}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>{unitFormMode === "create" ? "新增单位" : "编辑单位"}</DialogTitle></DialogHeader><div className="space-y-4 py-2"><div className="space-y-1.5"><Label>单位名称 *</Label><Input value={unitForm.unit_name} onChange={(event) => setUnitForm((current) => ({ ...current, unit_name: event.target.value }))} /></div></div><DialogFooter><Button variant="outline" className="cursor-pointer" onClick={() => setUnitFormOpen(false)} disabled={isSavingUnit}>取消</Button><Button className="cursor-pointer" disabled={isSavingUnit} onClick={() => { const unit_name = unitForm.unit_name.trim(); if (!unit_name) return showMessage("保存失败", "单位名称不能为空"); void save(async () => { const payload = { ...unitForm, unit_name }; if (unitFormMode === "create") await createGeneralCustomerUnit(payload); else if (editingUnitId !== null) await updateGeneralCustomerUnit(editingUnitId, payload) }, setIsSavingUnit, () => setUnitFormOpen(false)) }}>{isSavingUnit ? "保存中..." : "保存"}</Button></DialogFooter></DialogContent></Dialog>
      <ConfirmDialog open={deleteBrandTarget !== null} title="确认删除" description={`确定删除品牌 ${deleteBrandTarget?.name}？`} confirmLabel={isDeletingBrand ? "删除中..." : "删除"} variant="destructive" onConfirm={() => { if (!deleteBrandTarget) return; setIsDeletingBrand(true); void deleteGeneralCustomerBrand(deleteBrandTarget.id).then(load).then(() => setDeleteBrandTarget(null)).catch((error) => showMessage("删除失败", getErrorMessage(error))).finally(() => setIsDeletingBrand(false)) }} onCancel={() => setDeleteBrandTarget(null)} />
      <ConfirmDialog open={deleteShopTarget !== null} title="确认删除" description={`确定删除店铺 ${deleteShopTarget?.shop_name}？其下单位会一起删除。`} confirmLabel={isDeletingShop ? "删除中..." : "删除"} variant="destructive" onConfirm={() => { if (!deleteShopTarget) return; setIsDeletingShop(true); void deleteGeneralCustomerShop(deleteShopTarget.id).then(load).then(() => setDeleteShopTarget(null)).catch((error) => showMessage("删除失败", getErrorMessage(error))).finally(() => setIsDeletingShop(false)) }} onCancel={() => setDeleteShopTarget(null)} />
      <ConfirmDialog open={deleteUnitTarget !== null} title="确认删除" description={`确定删除单位 ${deleteUnitTarget?.unit_name}？此操作不可撤销。`} confirmLabel={isDeletingUnit ? "删除中..." : "删除"} variant="destructive" onConfirm={() => { if (!deleteUnitTarget) return; setIsDeletingUnit(true); void deleteGeneralCustomerUnit(deleteUnitTarget.id).then(load).then(() => setDeleteUnitTarget(null)).catch((error) => showMessage("删除失败", getErrorMessage(error))).finally(() => setIsDeletingUnit(false)) }} onCancel={() => setDeleteUnitTarget(null)} />
      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />
      <OperationLogDialog module="general_customer" title="一般客户操作日志" open={operationLogOpen} onOpenChange={setOperationLogOpen} />
    </div>
  )
}
