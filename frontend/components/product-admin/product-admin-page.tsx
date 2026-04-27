"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { ProductFormDialog } from "@/components/product-admin/product-form-dialog"
import { ProductTable } from "@/components/product-admin/product-table"
import { ProductTabs } from "@/components/product-admin/product-tabs"
import { ProductToolbar } from "@/components/product-admin/product-toolbar"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import { ThemeToggle } from "@/components/theme-toggle"
import { BRANDS, type BrandKey } from "@/lib/brands"
import { ApiError, deleteProduct, listProducts } from "@/lib/api"
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

  // ConfirmDialog state
  const [deleteTarget, setDeleteTarget] = useState<ProductListItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // MessageDialog state
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

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
  }, [brand, page, pageSize, reloadToken, submittedQuery])

  const currentBrandLabel = useMemo(() => {
    return BRANDS.find((item) => item.key === brand)?.label ?? "商品"
  }, [brand])

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

  return (
    <main className="min-h-svh bg-background px-6 py-10 text-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">商品信息档案</h1>
          </div>
          <ThemeToggle />
        </div>

        <Tabs
          value={brand}
          defaultValue={DEFAULT_BRAND}
          onValueChange={(value) => {
            setBrand(value as BrandKey)
            setPage(1)
          }}
        >
          <ProductTabs />

          <TabsContent value={brand} className="space-y-4 rounded-xl border border-border bg-muted/20 p-4">
            <div className="space-y-1">
              <h2 className="text-lg font-medium">{currentBrandLabel}</h2>
              <p className="text-sm text-muted-foreground">{isAllBrand(brand) ? "所有品牌商品汇总列表" : "当前品牌商品列表"}</p>
            </div>

            <ProductToolbar
              brand={brand}
              value={searchInput}
              isLoading={isLoading}
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

        <MessageDialog
          open={messageOpen}
          title={messageContent.title}
          description={messageContent.description}
          onClose={() => setMessageOpen(false)}
        />
      </div>
    </main>
  )
}
