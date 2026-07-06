"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronRight, Edit, History, Plus, Search, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { CounterpartyLedgerDialog } from "@/components/inventory-admin/counterparty-ledger-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import {
  ApiError,
  createGeneralCustomerBrand,
  createGeneralCustomerShop,
  deleteGeneralCustomerBrand,
  deleteGeneralCustomerShop,
  listGeneralCustomerBrands,
  listGeneralCustomerShops,
  updateGeneralCustomerBrand,
  updateGeneralCustomerShop,
} from "@/lib/api"
import type { GeneralCustomerBrandItem, GeneralCustomerShopItem } from "@/lib/types"

type GeneralCustomerShopsTabProps = {
  standalone?: boolean
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

const EMPTY_BRAND_FORM = { name: "" }
const EMPTY_SHOP_FORM = { customer_name: "", shop_name: "" }

export function GeneralCustomerShopsTab({ standalone = false }: GeneralCustomerShopsTabProps) {
  const [brands, setBrands] = useState<GeneralCustomerBrandItem[]>([])
  const [shops, setShops] = useState<GeneralCustomerShopItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null)

  const [brandFormOpen, setBrandFormOpen] = useState(false)
  const [brandFormMode, setBrandFormMode] = useState<"create" | "edit">("create")
  const [brandFormData, setBrandFormData] = useState({ ...EMPTY_BRAND_FORM })
  const [editingBrandId, setEditingBrandId] = useState<number | null>(null)
  const [isSavingBrand, setIsSavingBrand] = useState(false)
  const [deleteBrandTarget, setDeleteBrandTarget] = useState<GeneralCustomerBrandItem | null>(null)
  const [isDeletingBrand, setIsDeletingBrand] = useState(false)

  const [shopFormOpen, setShopFormOpen] = useState(false)
  const [shopFormMode, setShopFormMode] = useState<"create" | "edit">("create")
  const [shopFormData, setShopFormData] = useState({ ...EMPTY_SHOP_FORM })
  const [editingShopId, setEditingShopId] = useState<number | null>(null)
  const [isSavingShop, setIsSavingShop] = useState(false)
  const [deleteShopTarget, setDeleteShopTarget] = useState<GeneralCustomerShopItem | null>(null)
  const [isDeletingShop, setIsDeletingShop] = useState(false)
  const [ledgerTarget, setLedgerTarget] = useState<GeneralCustomerShopItem | null>(null)
  const [operationLogOpen, setOperationLogOpen] = useState(false)

  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const [brandResponse, shopResponse] = await Promise.all([listGeneralCustomerBrands(), listGeneralCustomerShops()])
      setBrands(brandResponse.items)
      setShops(shopResponse.items)
    } catch (error) {
      setBrands([])
      setShops([])
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
    return brands.filter((brand) => {
      const brandShops = shops.filter((shop) => shop.customer_name === brand.name)
      return [brand.name, ...brandShops.map((shop) => shop.shop_name)].some((value) =>
        value.toLowerCase().includes(term),
      )
    })
  }, [brands, shops, query])

  const activeBrand = useMemo(() => {
    if (filteredBrands.length === 0) return null
    if (selectedBrandId !== null) {
      return filteredBrands.find((brand) => brand.id === selectedBrandId) ?? filteredBrands[0]
    }
    return filteredBrands[0]
  }, [filteredBrands, selectedBrandId])

  useEffect(() => {
    if (filteredBrands.length === 0) {
      if (selectedBrandId !== null) setSelectedBrandId(null)
      return
    }
    if (selectedBrandId === null || !filteredBrands.some((brand) => brand.id === selectedBrandId)) {
      setSelectedBrandId(filteredBrands[0].id)
    }
  }, [filteredBrands, selectedBrandId])

  const visibleShops = useMemo(() => {
    if (!activeBrand) return []
    return shops.filter((shop) => shop.customer_name === activeBrand.name)
  }, [activeBrand, shops])

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const openCreateBrand = () => {
    setBrandFormMode("create")
    setBrandFormData({ ...EMPTY_BRAND_FORM })
    setEditingBrandId(null)
    setBrandFormOpen(true)
  }

  const openEditBrand = (brand: GeneralCustomerBrandItem) => {
    setBrandFormMode("edit")
    setBrandFormData({ name: brand.name })
    setEditingBrandId(brand.id)
    setBrandFormOpen(true)
  }

  const openCreateShop = () => {
    setShopFormMode("create")
    setShopFormData({ customer_name: activeBrand?.name || "", shop_name: "" })
    setEditingShopId(null)
    setShopFormOpen(true)
  }

  const openEditShop = (shop: GeneralCustomerShopItem) => {
    setShopFormMode("edit")
    setEditingShopId(shop.id)
    setShopFormData({ customer_name: shop.customer_name, shop_name: shop.shop_name })
    setShopFormOpen(true)
  }

  const handleSaveBrand = async () => {
    const name = brandFormData.name.trim()
    if (!name) return showMessage("保存失败", "品牌名称不能为空")
    setIsSavingBrand(true)
    try {
      if (brandFormMode === "create") {
        const result = await createGeneralCustomerBrand({ name })
        setSelectedBrandId(result.item.id)
      } else if (editingBrandId !== null) {
        const result = await updateGeneralCustomerBrand(editingBrandId, { name })
        setSelectedBrandId(result.item.id)
      }
      setBrandFormOpen(false)
      await load()
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSavingBrand(false)
    }
  }

  const handleSaveShop = async () => {
    const customer_name = shopFormData.customer_name.trim()
    const shop_name = shopFormData.shop_name.trim()
    if (!customer_name) return showMessage("保存失败", "品牌名称不能为空")
    if (!shop_name) return showMessage("保存失败", "店铺名称不能为空")
    setIsSavingShop(true)
    try {
      if (shopFormMode === "create") {
        await createGeneralCustomerShop({ customer_name, shop_name })
      } else if (editingShopId !== null) {
        await updateGeneralCustomerShop(editingShopId, { customer_name, shop_name })
      }
      setShopFormOpen(false)
      await load()
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSavingShop(false)
    }
  }

  const handleDeleteBrand = async () => {
    if (!deleteBrandTarget) return
    setIsDeletingBrand(true)
    try {
      await deleteGeneralCustomerBrand(deleteBrandTarget.id)
      setDeleteBrandTarget(null)
      await load()
    } catch (error) {
      showMessage("删除失败", getErrorMessage(error))
    } finally {
      setIsDeletingBrand(false)
    }
  }

  const handleDeleteShop = async () => {
    if (!deleteShopTarget) return
    setIsDeletingShop(true)
    try {
      await deleteGeneralCustomerShop(deleteShopTarget.id)
      setDeleteShopTarget(null)
      await load()
    } catch (error) {
      showMessage("删除失败", getErrorMessage(error))
    } finally {
      setIsDeletingShop(false)
    }
  }

  const searchBar = (
    <form
      className="flex flex-col gap-2 sm:flex-row sm:items-center"
      onSubmit={(event) => {
        event.preventDefault()
        setQuery(queryInput.trim())
      }}
    >
      <div className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
          placeholder="搜索品牌或店铺"
          className="pl-9"
          aria-label="搜索品牌店铺"
        />
      </div>
      <div className="flex items-center gap-2">
        <Button type="submit" disabled={isLoading} className="cursor-pointer">查询</Button>
        {(queryInput || query) && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            disabled={isLoading}
            onClick={() => {
              setQueryInput("")
              setQuery("")
            }}
            aria-label="清空搜索"
            className="cursor-pointer"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </form>
  )

  const brandList = (
    <div className="surface-panel p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-foreground">品牌</p>
        <Button size="sm" onClick={openCreateBrand} className="cursor-pointer">
          <Plus className="h-4 w-4" />
          <span className="ml-1.5">新增品牌</span>
        </Button>
      </div>
      <div className="mt-3">{searchBar}</div>
      <div className="mt-3 space-y-1.5">
        {isLoading && <div className="rounded-xl border border-border bg-card px-3 py-10 text-center text-sm text-muted-foreground">加载中...</div>}
        {!isLoading && filteredBrands.length === 0 && (
          <div className="rounded-xl border border-border bg-card px-3 py-10 text-center text-sm text-muted-foreground">
            {query ? "暂无匹配品牌" : "暂无品牌数据"}
          </div>
        )}
        {!isLoading && filteredBrands.map((brand) => {
          const selected = brand.id === activeBrand?.id
          return (
            <div
              key={brand.id}
              className={`group relative flex items-center gap-1 overflow-hidden rounded-xl border px-2 py-2 shadow-xs transition-all duration-150 ${selected
                  ? "border-foreground bg-muted/70 shadow-sm ring-1 ring-foreground/10"
                  : "border-border bg-card hover:-translate-y-px hover:border-foreground/25 hover:bg-muted/45 hover:shadow-sm"
                }`}
            >
              <span
                aria-hidden="true"
                className={`absolute inset-y-2 left-0 w-1 rounded-r-full bg-foreground transition-all duration-150 ${selected ? "opacity-100" : "opacity-0 group-hover:opacity-25"
                  }`}
              />
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => setSelectedBrandId(brand.id)}
                className="relative flex min-h-8 min-w-0 flex-1 cursor-pointer items-center justify-between gap-2 rounded-lg px-1.5 text-left text-sm outline-none transition-all active:translate-y-px focus-visible:ring-3 focus-visible:ring-ring/35"
              >
                <span className="truncate font-medium text-foreground">{brand.name}</span>
                <span className={`flex shrink-0 items-center gap-1.5 rounded-full px-1.5 py-0.5 text-xs transition-colors ${selected ? "bg-background text-foreground shadow-xs" : "text-muted-foreground"
                  }`}>
                  <span>{brand.shop_count} 家</span>
                  <ChevronRight className={`h-4 w-4 transition-all ${selected ? "translate-x-0.5 opacity-100" : "opacity-40 group-hover:translate-x-0.5 group-hover:opacity-70"}`} />
                </span>
              </button>
              <Button variant="ghost" size="icon" onClick={() => openEditBrand(brand)} className="relative h-8 w-8 cursor-pointer" aria-label={`编辑品牌 ${brand.name}`}>
                <Edit className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setDeleteBrandTarget(brand)} className="relative h-8 w-8 cursor-pointer" aria-label={`删除品牌 ${brand.name}`}>
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )

  const brandDetail = (
    <div className="surface-panel p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-foreground">{activeBrand?.name || "请选择品牌"}</p>
            {activeBrand && (
              <span className="rounded-full border border-border bg-muted/45 px-2.5 py-0.5 text-xs text-muted-foreground tabular-nums">
                {visibleShops.length} 家店铺
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">先选择品牌，再维护旗下店铺</p>
        </div>
        <Button size="sm" onClick={openCreateShop} disabled={!activeBrand} className="cursor-pointer">
          <Plus className="h-4 w-4" />
          <span className="ml-1.5">新增店铺</span>
        </Button>
      </div>

      <div className="mt-3 table-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-head-row">
                <th className="px-4 py-3 font-medium">店铺名称</th>
                <th className="px-4 py-3 w-32 font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && !activeBrand && (
                <tr>
                  <td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">请先新增或选择品牌</td>
                </tr>
              )}
              {!isLoading && activeBrand && visibleShops.length === 0 && (
                <tr>
                  <td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">该品牌暂无店铺</td>
                </tr>
              )}
              {!isLoading && visibleShops.map((shop) => (
                <tr
                  key={shop.id}
                  className="table-row cursor-pointer"
                  onClick={() => setLedgerTarget(shop)}
                  title="点击查看单据"
                >
                  <td className="px-4 py-2.5 font-medium">{shop.shop_name}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-0.5">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(event) => {
                          event.stopPropagation()
                          openEditShop(shop)
                        }}
                        className="cursor-pointer"
                        aria-label={`编辑 ${shop.customer_name} / ${shop.shop_name}`}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(event) => {
                          event.stopPropagation()
                          setDeleteShopTarget(shop)
                        }}
                        className="cursor-pointer"
                        aria-label={`删除 ${shop.customer_name} / ${shop.shop_name}`}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )

  const dialogs = (
    <>
      <Dialog open={brandFormOpen} onOpenChange={setBrandFormOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{brandFormMode === "create" ? "新增品牌" : "编辑品牌"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="brand-name">品牌 *</Label>
              <Input id="brand-name" value={brandFormData.name} onChange={(e) => setBrandFormData((prev) => ({ ...prev, name: e.target.value }))} placeholder="例如：烟斗" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBrandFormOpen(false)} disabled={isSavingBrand} className="cursor-pointer">取消</Button>
            <Button onClick={handleSaveBrand} disabled={isSavingBrand} className="cursor-pointer">{isSavingBrand ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={shopFormOpen} onOpenChange={setShopFormOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{shopFormMode === "create" ? "新增店铺" : "编辑店铺"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="shop-brand-name">品牌 *</Label>
              <Input id="shop-brand-name" value={shopFormData.customer_name} disabled={standalone && shopFormMode === "create"} onChange={(e) => setShopFormData((prev) => ({ ...prev, customer_name: e.target.value }))} placeholder="例如：烟斗" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="shop-name">店铺名称 *</Label>
              <Input id="shop-name" value={shopFormData.shop_name} onChange={(e) => setShopFormData((prev) => ({ ...prev, shop_name: e.target.value }))} placeholder="例如：烟斗唯品会店铺" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShopFormOpen(false)} disabled={isSavingShop} className="cursor-pointer">取消</Button>
            <Button onClick={handleSaveShop} disabled={isSavingShop} className="cursor-pointer">{isSavingShop ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteBrandTarget !== null}
        title="确认删除"
        description={`确定删除品牌 ${deleteBrandTarget?.name}？该品牌下的店铺会一起删除。`}
        confirmLabel={isDeletingBrand ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDeleteBrand}
        onCancel={() => setDeleteBrandTarget(null)}
      />

      <ConfirmDialog
        open={deleteShopTarget !== null}
        title="确认删除"
        description={`确定删除店铺 ${deleteShopTarget?.customer_name} / ${deleteShopTarget?.shop_name}？此操作不可撤销。`}
        confirmLabel={isDeletingShop ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDeleteShop}
        onCancel={() => setDeleteShopTarget(null)}
      />

      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />

      <CounterpartyLedgerDialog
        open={ledgerTarget !== null}
        counterpartyType="customer"
        name={ledgerTarget?.shop_name || ""}
        onOpenChange={(open) => {
          if (!open) setLedgerTarget(null)
        }}
      />

      <OperationLogDialog
        module="general_customer"
        title="一般客户操作日志"
        open={operationLogOpen}
        onOpenChange={setOperationLogOpen}
      />
    </>
  )

  return standalone ? (
    <div className="app-page">
      <div className="app-content">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="page-title">品牌店铺</h1>
            </div>
            <span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">{brands.length} 个品牌</span>
          </div>
          <Button size="sm" variant="outline" onClick={() => setOperationLogOpen(true)} className="cursor-pointer">
            <History className="h-4 w-4" />
            <span className="ml-1.5">操作日志</span>
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          {brandList}
          {brandDetail}
        </div>
      </div>

      {dialogs}
    </div>
  ) : (
    <div className="surface-panel p-4">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-foreground">品牌店铺管理</p>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setOperationLogOpen(true)} className="cursor-pointer">
              <History className="h-4 w-4" />
              <span className="ml-1.5">操作日志</span>
            </Button>
            <Button size="sm" onClick={openCreateBrand} className="cursor-pointer">
              <Plus className="h-4 w-4" />
              <span className="ml-1.5">新增品牌</span>
            </Button>
          </div>
        </div>
        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          {brandList}
          {brandDetail}
        </div>
      </div>

      {dialogs}
    </div>
  )
}
