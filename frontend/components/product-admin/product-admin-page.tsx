"use client"

import { useCallback, useEffect, useState } from "react"
import { RotateCcw, Trash2, X } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { ProductFormDialog } from "@/components/product-admin/product-form-dialog"
import { ProductTable } from "@/components/product-admin/product-table"
import { ProductTabs } from "@/components/product-admin/product-tabs"
import { ProductToolbar } from "@/components/product-admin/product-toolbar"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Tabs, TabsContent } from "@/components/ui/tabs"

import { PRODUCT_ARCHIVE_BRANDS, resolveProductArchiveBrands, type ProductArchiveBrandKey, type ProductArchiveRecordBrandKey } from "@/lib/brands"
import { ApiError, batchDeleteProducts, deleteProduct, getProductYears, listProductArchiveBrands, listProductRecycleBin, listProducts, permanentlyDeleteProduct, restoreProductFromRecycleBin, type SupplierBrandItem } from "@/lib/api"
import type { ProductListItem, ProductRecycleItem } from "@/lib/types"

const DEFAULT_BRAND = PRODUCT_ARCHIVE_BRANDS.find((item) => item.key !== "all")?.key ?? PRODUCT_ARCHIVE_BRANDS[0].key
const PAGE_SIZES = [10, 50, 100]

const isAllBrand = (b: ProductArchiveBrandKey) => b === "all"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message || `请求失败（${error.status}）`
  }

  if (error instanceof Error) {
    return error.message
  }

  return "加载商品数据时发生未知错误"
}

export function ProductAdminPage() {
  const { hasPermission } = useAuth()
  const [brand, setBrand] = useState<ProductArchiveBrandKey>(DEFAULT_BRAND)
  const [routeContextReady, setRouteContextReady] = useState(false)
  const [year, setYear] = useState("")
  const [availableYears, setAvailableYears] = useState<string[]>([])
  const [searchInput, setSearchInput] = useState("")
  const [submittedQuery, setSubmittedQuery] = useState("")
  const [skuPrefixInput, setSkuPrefixInput] = useState("")
  const [submittedSkuPrefix, setSubmittedSkuPrefix] = useState("")
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0])
  const [reloadToken, setReloadToken] = useState(0)
  const [items, setItems] = useState<ProductListItem[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create")
  const [selectedItem, setSelectedItem] = useState<ProductListItem | null>(null)
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [managedBrands, setManagedBrands] = useState<SupplierBrandItem[]>([])
  const productArchiveBrands = resolveProductArchiveBrands(managedBrands)
  const [recycleOpen, setRecycleOpen] = useState(false)
  const [recycleBrand, setRecycleBrand] = useState<ProductArchiveBrandKey | "all">("all")
  const [recycleItems, setRecycleItems] = useState<ProductRecycleItem[]>([])
  const [recycleTotal, setRecycleTotal] = useState(0)
  const [recyclePage, setRecyclePage] = useState(1)
  const [isRecycleLoading, setIsRecycleLoading] = useState(false)
  const [recycleActionItem, setRecycleActionItem] = useState<ProductRecycleItem | null>(null)
  const [recycleAction, setRecycleAction] = useState<"restore" | "permanent_delete" | null>(null)
  const [isRecycleActioning, setIsRecycleActioning] = useState(false)

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())

  // ConfirmDialog state
  const [deleteTarget, setDeleteTarget] = useState<ProductListItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // Batch delete confirm state
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [isBatchDeleting, setIsBatchDeleting] = useState(false)

  // MessageDialog state
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const nextBrand = params.get("brand")
    const nextQuery = params.get("query") || ""
    if (nextBrand && PRODUCT_ARCHIVE_BRANDS.some((item) => item.key === nextBrand)) {
      setBrand(nextBrand)
    }
    if (nextQuery) {
      setSearchInput(nextQuery)
      setSubmittedQuery(nextQuery)
    }
    setRouteContextReady(true)
  }, [])

  useEffect(() => {
    if (!routeContextReady) return
    if (isAllBrand(brand)) {
      setAvailableYears([])
      return
    }
    async function loadYears() {
      try {
        const res = await getProductYears(brand)
        setAvailableYears(res.years)
      } catch {
        setAvailableYears([])
      }
    }
    void loadYears()
  }, [brand, routeContextReady])

  useEffect(() => {
    let cancelled = false

    void listProductArchiveBrands()
      .then((response) => {
        if (!cancelled) setManagedBrands(response.items)
      })
      .catch(() => {
        if (!cancelled) setManagedBrands([])
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadProducts() {
      setIsLoading(true)
      setError(null)

      try {
        const response = await listProducts({
          brand,
          page,
          pageSize: pageSize,
          query: submittedQuery || undefined,
          skuPrefix: submittedSkuPrefix || undefined,
          year: year || undefined,
        })

        if (cancelled) {
          return
        }

        setItems(response.items)
        setTotal(response.total)
      } catch (loadError) {
        if (cancelled) {
          return
        }

        setItems([])
        setTotal(0)
        setError(getErrorMessage(loadError))
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadProducts()

    return () => {
      cancelled = true
    }
  }, [brand, year, page, pageSize, reloadToken, routeContextReady, submittedQuery, submittedSkuPrefix])

  // Clear selection on page/brand/search change
  useEffect(() => {
    setSelectedIds(new Set())
  }, [brand, year, page, submittedQuery, submittedSkuPrefix])

  const handleSaved = async () => {
    setReloadToken((current) => current + 1)
  }

  const handleDeleteRequest = useCallback((item: ProductListItem) => {
    setDeleteTarget(item)
  }, [])

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return

    setIsDeleting(true)
    try {
      await deleteProduct(deleteTarget.brand as ProductArchiveRecordBrandKey, deleteTarget.id)
      setSelectedIds((prev) => {
        const next = new Set(prev)
        next.delete(deleteTarget.id)
        return next
      })
      setReloadToken((current) => current + 1)
    } catch (deleteError) {
      setMessageContent({ title: "删除失败", description: getErrorMessage(deleteError) })
      setMessageOpen(true)
    } finally {
      setIsDeleting(false)
      setDeleteTarget(null)
    }
  }

  const showMessage = useCallback((title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }, [])

  const loadRecycleBin = useCallback(async () => {
    setIsRecycleLoading(true)
    try {
      const response = await listProductRecycleBin({
        brand: recycleBrand === "all" ? undefined : recycleBrand,
        page: recyclePage,
        pageSize: 20,
      })
      setRecycleItems(response.items)
      setRecycleTotal(response.total)
    } catch (loadError) {
      setRecycleItems([])
      setRecycleTotal(0)
      showMessage("回收站加载失败", getErrorMessage(loadError))
    } finally {
      setIsRecycleLoading(false)
    }
  }, [recycleBrand, recyclePage, showMessage])

  useEffect(() => {
    if (recycleOpen) void loadRecycleBin()
  }, [loadRecycleBin, recycleOpen])

  const requestRecycleAction = (item: ProductRecycleItem, action: "restore" | "permanent_delete") => {
    setRecycleActionItem(item)
    setRecycleAction(action)
  }

  const handleRecycleAction = async () => {
    if (!recycleActionItem || !recycleAction) return
    setIsRecycleActioning(true)
    try {
      const brandKey = recycleActionItem.brand as ProductArchiveRecordBrandKey
      if (recycleAction === "restore") {
        await restoreProductFromRecycleBin(brandKey, recycleActionItem.id)
      } else {
        await permanentlyDeleteProduct(brandKey, recycleActionItem.id)
      }
      setRecycleActionItem(null)
      setRecycleAction(null)
      setReloadToken((current) => current + 1)
      await loadRecycleBin()
    } catch (actionError) {
      showMessage(recycleAction === "restore" ? "恢复失败" : "彻底删除失败", getErrorMessage(actionError))
    } finally {
      setIsRecycleActioning(false)
    }
  }

  const handleToggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  const handleToggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      const allSelected = items.every((item) => prev.has(item.id))
      if (allSelected) {
        const next = new Set(prev)
        for (const item of items) {
          next.delete(item.id)
        }
        return next
      }
      const next = new Set(prev)
      for (const item of items) {
        next.add(item.id)
      }
      return next
    })
  }, [items])

  const handleBatchDeleteRequest = useCallback(() => {
    setBatchDeleteOpen(true)
  }, [])

  const handleBatchDeleteConfirm = async () => {
    setIsBatchDeleting(true)
    try {
      await batchDeleteProducts(brand as ProductArchiveRecordBrandKey, Array.from(selectedIds))
      setSelectedIds(new Set())
      setReloadToken((current) => current + 1)
    } catch (deleteError) {
      setMessageContent({ title: "批量删除失败", description: getErrorMessage(deleteError) })
      setMessageOpen(true)
    } finally {
      setIsBatchDeleting(false)
      setBatchDeleteOpen(false)
    }
  }

  const showBatchDelete = !isAllBrand(brand) && selectedIds.size > 0
  const canManageProducts = hasPermission("product.manage")
  const canExportProducts = hasPermission("product.export")
  const canImportProducts = hasPermission("product.import")
  const canSelectProducts = canManageProducts || canExportProducts

  return (
    <div className="app-page">
      <div className="app-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">商品信息档案</h1>
            <p className="page-subtitle">
              管理品牌商品基础资料、图片匹配和批量导入导出
            </p>
          </div>
          <div className="flex h-9 items-center rounded-full border border-border bg-muted/45 px-3 text-sm text-muted-foreground">
            共 {total} 条
          </div>
        </div>

        <Tabs
          value={brand}
          defaultValue={DEFAULT_BRAND}
          onValueChange={(value) => {
            setAvailableYears([])
            setBrand(value as ProductArchiveBrandKey)
            setYear("")
            setPage(1)
          }}
        >
          <div className="sticky top-0 z-30 -mx-5 bg-background/95 px-5 py-3 shadow-[0_8px_18px_-18px_rgb(0_0_0_/_0.65)] backdrop-blur">
            <div className="surface-panel p-1.5">
              <ProductTabs brands={productArchiveBrands} />
            </div>

            <TabsContent value={brand} className="mt-4 space-y-4">
              {!isAllBrand(brand) && (
                <div className="flex min-h-8 items-center gap-1.5">
                  {availableYears.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {["", ...availableYears].map((y) => (
                        <button
                          key={y}
                          onClick={() => { setYear(y); setPage(1) }}
                          className={`cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-150 ${year === y
                              ? "bg-primary text-primary-foreground shadow-sm"
                              : "bg-muted text-muted-foreground hover:bg-muted-foreground/20 hover:text-foreground"
                            }`}
                        >
                          {y || "全部"}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <ProductToolbar
                brand={brand}
                year={year}
                value={searchInput}
                query={submittedQuery}
                prefixValue={skuPrefixInput}
                skuPrefix={submittedSkuPrefix}
                isLoading={isLoading}
                selectedIds={selectedIds}
                canExport={canExportProducts}
                canImport={canImportProducts}
                canRefreshImages={canManageProducts}
                onValueChange={setSearchInput}
                onPrefixValueChange={setSkuPrefixInput}
                onSearch={() => {
                  setPage(1)
                  setSubmittedQuery(searchInput.trim())
                  setSubmittedSkuPrefix(skuPrefixInput.trim())
                }}
                onClear={() => {
                  setSearchInput("")
                  setSkuPrefixInput("")
                  setPage(1)
                  setSubmittedQuery("")
                  setSubmittedSkuPrefix("")
                }}
                onRefresh={() => {
                  setReloadToken((current) => current + 1)
                }}
                onOpenLogs={() => setOperationLogOpen(true)}
                onOpenRecycleBin={canManageProducts ? () => {
                  setRecycleBrand(isAllBrand(brand) ? "all" : brand)
                  setRecyclePage(1)
                  setRecycleOpen(true)
                } : undefined}
                onImportComplete={(skus: string[]) => {
                  const query = skus.join(",")
                  setSearchInput(query)
                  setSubmittedQuery(query)
                  setSkuPrefixInput("")
                  setSubmittedSkuPrefix("")
                  setPage(1)
                }}
                onCreate={isAllBrand(brand) || !canManageProducts ? undefined : () => {
                  setDialogMode("create")
                  setSelectedItem(null)
                  setIsDialogOpen(true)
                }}
                onMessage={showMessage}
              />
            </TabsContent>
          </div>

          <TabsContent value={brand} className="mt-4">
            <ProductTable
              items={items}
              total={total}
              page={page}
              pageSize={pageSize}
              pageSizes={PAGE_SIZES}
              isLoading={isLoading}
              error={error}
              selectable={!isAllBrand(brand) && canSelectProducts}
              selectedIds={selectedIds}
              onToggleSelect={handleToggleSelect}
              onToggleSelectAll={handleToggleSelectAll}
              onBatchDelete={showBatchDelete && canManageProducts ? handleBatchDeleteRequest : undefined}
              onEdit={isAllBrand(brand) || !canManageProducts ? undefined : (item) => {
                setDialogMode("edit")
                setSelectedItem(item)
                setIsDialogOpen(true)
              }}
              onDelete={isAllBrand(brand) || !canManageProducts ? undefined : handleDeleteRequest}
              onPreviewImage={(item) => {
                if (!item.image_url) return
                setPreviewImage({
                  src: `/api${item.image_url}`,
                  alt: item.sku || item.original_sku || "商品图片",
                })
              }}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
              onClearSelection={() => setSelectedIds(new Set())}
            />
          </TabsContent>
        </Tabs>

        <ProductFormDialog
          key={dialogMode === "edit" && selectedItem ? `edit-${selectedItem.brand}-${selectedItem.id}` : `create-${brand}-${isDialogOpen ? "open" : "closed"}`}
          open={isDialogOpen}
          mode={dialogMode}
          item={selectedItem}
          onOpenChange={(open) => {
            setIsDialogOpen(open)
            if (!open) {
              setSelectedItem(null)
            }
          }}
          onSaved={handleSaved}
          brands={productArchiveBrands}
        />

        <OperationLogDialog
          module="product"
          title="商品信息档案操作日志"
          open={operationLogOpen}
          onOpenChange={setOperationLogOpen}
        />

        <ConfirmDialog
          open={deleteTarget !== null}
          title="确认删除"
          description={`确定将商品 ${deleteTarget?.original_sku || deleteTarget?.sku || deleteTarget?.id} 移入回收站吗？可在回收站中恢复或彻底删除。`}
          confirmLabel={isDeleting ? "处理中..." : "移入回收站"}
          variant="destructive"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />

        <ConfirmDialog
          open={batchDeleteOpen}
          title="确认批量删除"
          description={`确定将选中的 ${selectedIds.size} 条商品移入回收站吗？可在回收站中恢复或彻底删除。`}
          confirmLabel={isBatchDeleting ? "处理中..." : "移入回收站"}
          variant="destructive"
          onConfirm={handleBatchDeleteConfirm}
          onCancel={() => setBatchDeleteOpen(false)}
        />

        <MessageDialog
          open={messageOpen}
          title={messageContent.title}
          description={messageContent.description}
          onClose={() => setMessageOpen(false)}
        />
        <Dialog open={recycleOpen} onOpenChange={setRecycleOpen}>
          <DialogContent className="max-h-[88svh] max-w-[min(96vw,1100px)] overflow-hidden p-0">
            <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-5 py-4">
              <DialogTitle>商品信息档案回收站</DialogTitle>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 cursor-pointer"
                onClick={() => setRecycleOpen(false)}
                aria-label="关闭商品信息档案回收站"
                title="关闭"
              >
                <X className="h-4 w-4" />
              </Button>
            </DialogHeader>
            <div className="space-y-4 overflow-y-auto p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1.5">
                  {[{ key: "all" as const, label: "全部品牌" }, ...productArchiveBrands.filter((item) => item.key !== "all")].map((item) => (
                    <Button
                      key={item.key}
                      type="button"
                      size="sm"
                      variant={recycleBrand === item.key ? "default" : "outline"}
                      className="cursor-pointer"
                      onClick={() => { setRecycleBrand(item.key); setRecyclePage(1) }}
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
                <span className="text-sm text-muted-foreground">共 {recycleTotal} 条</span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[780px] text-sm">
                  <thead><tr className="table-head-row"><th className="px-3 py-2 text-left font-medium">品牌</th><th className="px-3 py-2 text-left font-medium">货号</th><th className="px-3 py-2 text-left font-medium">品名</th><th className="px-3 py-2 text-left font-medium">颜色</th><th className="px-3 py-2 text-left font-medium">删除时间</th><th className="px-3 py-2 text-center font-medium">操作</th></tr></thead>
                  <tbody className="divide-y divide-border">
                    {isRecycleLoading && <tr><td colSpan={6} className="px-3 py-12 text-center text-muted-foreground">加载中...</td></tr>}
                    {!isRecycleLoading && recycleItems.length === 0 && <tr><td colSpan={6} className="px-3 py-12 text-center text-muted-foreground">回收站暂无商品</td></tr>}
                    {!isRecycleLoading && recycleItems.map((item) => <tr key={`${item.brand}-${item.id}`} className="table-row"><td className="px-3 py-2">{productArchiveBrands.find((brandItem) => brandItem.key === item.brand)?.label || item.brand}</td><td className="px-3 py-2 font-medium">{item.original_sku || item.sku || "-"}</td><td className="px-3 py-2">{item.product_name || "-"}</td><td className="px-3 py-2">{item.color || "-"}</td><td className="px-3 py-2 whitespace-nowrap text-xs text-muted-foreground">{item.deleted_at ? new Date(item.deleted_at).toLocaleString("zh-CN", { hour12: false }) : "-"}</td><td className="px-3 py-2"><div className="flex justify-center gap-1"><Button type="button" variant="ghost" size="sm" className="cursor-pointer" onClick={() => requestRecycleAction(item, "restore")}><RotateCcw className="mr-1 h-3.5 w-3.5" />恢复</Button><Button type="button" variant="ghost" size="sm" className="cursor-pointer text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={() => requestRecycleAction(item, "permanent_delete")}><Trash2 className="mr-1 h-3.5 w-3.5" />彻底删除</Button></div></td></tr>)}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-end gap-3">
                <Button type="button" size="sm" variant="outline" className="cursor-pointer" disabled={recyclePage <= 1 || isRecycleLoading} onClick={() => setRecyclePage((value) => value - 1)}>上一页</Button>
                <span className="text-sm text-muted-foreground">{recyclePage} / {Math.max(1, Math.ceil(recycleTotal / 20))}</span>
                <Button type="button" size="sm" variant="outline" className="cursor-pointer" disabled={recyclePage >= Math.max(1, Math.ceil(recycleTotal / 20)) || isRecycleLoading} onClick={() => setRecyclePage((value) => value + 1)}>下一页</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
        <ConfirmDialog
          open={recycleActionItem !== null}
          title={recycleAction === "restore" ? "确认恢复商品" : "确认彻底删除商品"}
          description={recycleAction === "restore" ? `确定恢复商品 ${recycleActionItem?.original_sku || recycleActionItem?.sku || recycleActionItem?.id} 吗？` : `确定彻底删除商品 ${recycleActionItem?.original_sku || recycleActionItem?.sku || recycleActionItem?.id} 吗？此操作不可恢复。`}
          confirmLabel={isRecycleActioning ? "处理中..." : recycleAction === "restore" ? "恢复" : "彻底删除"}
          variant={recycleAction === "permanent_delete" ? "destructive" : "default"}
          onConfirm={() => void handleRecycleAction()}
          onCancel={() => !isRecycleActioning && (setRecycleActionItem(null), setRecycleAction(null))}
        />
        <Dialog open={previewImage !== null} onOpenChange={(open) => !open && setPreviewImage(null)}>
          <DialogContent className="max-h-[92svh] max-w-[min(94vw,1120px)] overflow-hidden bg-background p-0 shadow-2xl">
            <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
              <DialogTitle className="text-base font-semibold">原图预览</DialogTitle>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setPreviewImage(null)}
                aria-label="关闭原图预览"
              >
                <X className="h-4 w-4" />
              </Button>
            </DialogHeader>
            {previewImage ? (
              <div className="flex h-[min(78svh,760px)] items-center justify-center bg-muted/20 p-4 sm:p-6">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={previewImage.src}
                  alt={previewImage.alt}
                  className="max-h-full w-auto max-w-full rounded-md object-contain shadow-sm"
                />
              </div>
            ) : null}
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
