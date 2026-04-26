"use client"

import { useEffect, useMemo, useState } from "react"

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
const PAGE_SIZE = 10

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
  const [reloadToken, setReloadToken] = useState(0)
  const [items, setItems] = useState<ProductListItem[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create")
  const [selectedItem, setSelectedItem] = useState<ProductListItem | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadProducts() {
      setIsLoading(true)
      setError(null)

      try {
        const response = await listProducts({
          brand,
          page,
          pageSize: PAGE_SIZE,
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
  }, [brand, page, reloadToken, submittedQuery])

  const currentBrandLabel = useMemo(() => {
    return BRANDS.find((item) => item.key === brand)?.label ?? "商品"
  }, [brand])

  const handleSaved = async () => {
    setReloadToken((current) => current + 1)
  }

  const handleDelete = async (item: ProductListItem) => {
    if (!confirm(`确定删除商品 ${item.original_sku || item.sku || item.id}？`)) {
      return
    }

    try {
      await deleteProduct(item.brand, item.id)
      setReloadToken((current) => current + 1)
    } catch (deleteError) {
      alert(getErrorMessage(deleteError))
    }
  }

  return (
    <main className="min-h-svh bg-background px-6 py-10 text-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">商品信息档案</h1>
            <p className="text-sm text-muted-foreground">按品牌查看商品列表，并支持原始货号搜索。</p>
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
              <p className="text-sm text-muted-foreground">当前品牌商品列表</p>
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
              onCreate={() => {
                setDialogMode("create")
                setSelectedItem(null)
                setIsDialogOpen(true)
              }}
            />

            <ProductTable
              items={items}
              total={total}
              page={page}
              pageSize={PAGE_SIZE}
              isLoading={isLoading}
              error={error}
              onEdit={(item) => {
                setDialogMode("edit")
                setSelectedItem(item)
                setIsDialogOpen(true)
              }}
              onDelete={handleDelete}
              onPageChange={setPage}
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
      </div>
    </main>
  )
}
