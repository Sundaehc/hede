"use client"

import { useCallback, useEffect, useState } from "react"

import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { ProductFormDialog } from "@/components/product-admin/product-form-dialog"
import { ProductTable } from "@/components/product-admin/product-table"
import { ProductTabs } from "@/components/product-admin/product-tabs"
import { ProductToolbar } from "@/components/product-admin/product-toolbar"
import { Tabs, TabsContent } from "@/components/ui/tabs"

import { BRANDS, type BrandKey } from "@/lib/brands"
import { ApiError, batchDeleteProducts, deleteProduct, getProductYears, listProducts } from "@/lib/api"
import type { ProductListItem } from "@/lib/types"

const DEFAULT_BRAND = BRANDS[0].key
const PAGE_SIZES = [10, 50, 100]

const isAllBrand = (b: BrandKey) => b === "all"

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
  const [brand, setBrand] = useState<BrandKey>(DEFAULT_BRAND)
  const [year, setYear] = useState("")
  const [availableYears, setAvailableYears] = useState<string[]>([])
  const [searchInput, setSearchInput] = useState("")
  const [submittedQuery, setSubmittedQuery] = useState("")
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
    if (isAllBrand(brand)) {
      setAvailableYears([])
      return
    }
    async function loadYears() {
      try {
        const res = await getProductYears(brand as BrandKey)
        setAvailableYears(res.years)
      } catch {
        setAvailableYears([])
      }
    }
    void loadYears()
  }, [brand])

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
  }, [brand, year, page, pageSize, reloadToken, submittedQuery])

  // Clear selection on page/brand/search change
  useEffect(() => {
    setSelectedIds(new Set())
  }, [brand, year, page, submittedQuery])

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
      await deleteProduct(deleteTarget.brand, deleteTarget.id)
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
      await batchDeleteProducts(brand as BrandKey, Array.from(selectedIds))
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

  const showMessage = useCallback((title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }, [])

  const showBatchDelete = !isAllBrand(brand) && selectedIds.size > 0

  return (
    <div className="app-page">
      <div className="app-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">商品信息档案</h1>
            <p className="page-subtitle">管理品牌商品基础资料、图片匹配和批量导入导出</p>
          </div>
          <div className="flex h-9 items-center rounded-full border border-border bg-muted/45 px-3 text-sm text-muted-foreground">
            共 {total} 条
          </div>
        </div>

        <Tabs
          value={brand}
          defaultValue={DEFAULT_BRAND}
          onValueChange={(value) => {
            setBrand(value as BrandKey)
            setYear("")
            setPage(1)
          }}
        >
          <div className="surface-panel p-1.5">
            <ProductTabs />
          </div>

          <TabsContent value={brand} className="mt-4 space-y-4">
            {!isAllBrand(brand) && (
              <div className="flex items-center gap-1.5">
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
              value={searchInput}
              isLoading={isLoading}
              selectedIds={selectedIds}
              onValueChange={setSearchInput}
              onSearch={() => {
                setPage(1)
                setSubmittedQuery(searchInput.trim())
              }}
              onClear={() => {
                setSearchInput("")
                setPage(1)
                setSubmittedQuery("")
              }}
              onRefresh={() => {
                setReloadToken((current) => current + 1)
              }}
              onImportComplete={(skus: string[]) => {
                const query = skus.join(",")
                setSearchInput(query)
                setSubmittedQuery(query)
                setPage(1)
              }}
              onCreate={isAllBrand(brand) ? undefined : () => {
                setDialogMode("create")
                setSelectedItem(null)
                setIsDialogOpen(true)
              }}
              onMessage={showMessage}
            />

            <ProductTable
              items={items}
              total={total}
              page={page}
              pageSize={pageSize}
              pageSizes={PAGE_SIZES}
              isLoading={isLoading}
              error={error}
              selectable={!isAllBrand(brand)}
              selectedIds={selectedIds}
              onToggleSelect={handleToggleSelect}
              onToggleSelectAll={handleToggleSelectAll}
              onBatchDelete={showBatchDelete ? handleBatchDeleteRequest : undefined}
              onEdit={isAllBrand(brand) ? undefined : (item) => {
                setDialogMode("edit")
                setSelectedItem(item)
                setIsDialogOpen(true)
              }}
              onDelete={isAllBrand(brand) ? undefined : handleDeleteRequest}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
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
        />

        <ConfirmDialog
          open={deleteTarget !== null}
          title="确认删除"
          description={`确定删除商品 ${deleteTarget?.original_sku || deleteTarget?.sku || deleteTarget?.id}？此操作不可撤销。`}
          confirmLabel={isDeleting ? "删除中..." : "删除"}
          variant="destructive"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />

        <ConfirmDialog
          open={batchDeleteOpen}
          title="确认批量删除"
          description={`确定删除选中的 ${selectedIds.size} 条商品？此操作不可撤销。`}
          confirmLabel={isBatchDeleting ? "删除中..." : "删除"}
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
      </div>
    </div>
  )
}
