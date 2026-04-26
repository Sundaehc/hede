import type { ProductListItem } from "@/lib/types"
import { FIELD_GROUPS, FIELD_LABELS } from "@/lib/fields"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

type ProductTableProps = {
  items: ProductListItem[]
  total: number
  page: number
  pageSize: number
  isLoading: boolean
  error: string | null
  onEdit: (item: ProductListItem) => void
  onDelete: (item: ProductListItem) => void
  onPageChange: (page: number) => void
}

function getTotalPages(total: number, pageSize: number) {
  return Math.max(1, Math.ceil(total / pageSize))
}

function ProductImage({ item }: { item: ProductListItem }) {
  const src = item.image_url ? `/api${item.image_url}` : null

  if (!src) {
    return (
      <div className="flex h-32 w-32 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-xs text-muted-foreground">
        暂无图片
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={item.sku || item.original_sku || "商品图片"}
      className="h-32 w-32 shrink-0 object-contain"
      loading="lazy"
    />
  )
}

function ProductCard({ item, onEdit, onDelete }: { item: ProductListItem; onEdit: (item: ProductListItem) => void; onDelete: (item: ProductListItem) => void }) {
  return (
    <div className="flex gap-4 rounded-xl border border-border bg-card p-4">
      <ProductImage item={item} />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium" data-testid={`card-title-${item.id}`}>
              {item.original_sku || item.sku || "-"}
            </p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => onEdit(item)} className="cursor-pointer">
              编辑
            </Button>
            <Button type="button" variant="outline" size="sm" className="text-destructive hover:text-destructive cursor-pointer" onClick={() => onDelete(item)} >
              删除
            </Button>
          </div>
        </div>
        <div className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {FIELD_GROUPS.map((group) =>
            group.fields.map((field) => {
              const value = item[field as keyof ProductListItem]
              if (value === null || value === undefined || value === "") return null
              return (
                <div key={field} className="flex gap-1">
                  <span className="shrink-0 text-muted-foreground">{FIELD_LABELS[field]}:</span>
                  <span className="truncate">{String(value)}</span>
                </div>
              )
            }),
          )}
        </div>
      </div>
    </div>
  )
}

export function ProductTable({
  items,
  total,
  page,
  pageSize,
  isLoading,
  error,
  onEdit,
  onDelete,
  onPageChange,
}: ProductTableProps) {
  const totalPages = getTotalPages(total, pageSize)
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = total === 0 ? 0 : Math.min(page * pageSize, total)

  if (error) {
    return (
      <Alert className="border-destructive/30">
        <AlertTitle>加载失败</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )
  }

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
        正在加载商品数据...
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          共 {total} 条，当前显示 {start}-{end}
        </p>
        <p>
          第 {page} / {totalPages} 页
        </p>
      </div>

      <div className="space-y-3">
        {items.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
            暂无商品数据
          </div>
        ) : (
          items.map((item) => (
            <ProductCard key={`${item.brand}-${item.id}`} item={item} onEdit={onEdit} onDelete={onDelete} />
          ))
        )}
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => onPageChange(page - 1)} disabled={page <= 1} className="cursor-pointer">
          上一页
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages || items.length === 0}
          className="cursor-pointer"
        >
          下一页
        </Button>
      </div>
    </div>
  )
}
