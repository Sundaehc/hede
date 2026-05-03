import type { ProductListItem } from "@/lib/types"
import { CARD_DISPLAY_FIELDS, FIELD_GROUPS, FIELD_LABELS } from "@/lib/fields"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { Select } from "@/components/ui/select"

type ProductTableProps = {
  items: ProductListItem[]
  total: number
  page: number
  pageSize: number
  pageSizes: number[]
  isLoading: boolean
  error: string | null
  onEdit?: (item: ProductListItem) => void
  onDelete?: (item: ProductListItem) => void
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

function getTotalPages(total: number, pageSize: number) {
  return Math.max(1, Math.ceil(total / pageSize))
}

function buildPageRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const pages: (number | "ellipsis")[] = [1]

  if (current > 3) {
    pages.push("ellipsis")
  }

  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  if (current < total - 2) {
    pages.push("ellipsis")
  }

  pages.push(total)
  return pages
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

function ProductCard({ item, onEdit, onDelete }: { item: ProductListItem; onEdit?: (item: ProductListItem) => void; onDelete?: (item: ProductListItem) => void }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border bg-card p-4">
      <ProductImage item={item} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {/* Header: SKU + actions */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold" data-testid={`card-title-${item.id}`}>
              {item.sku || "-"}
            </p>
            {item.original_sku ? (
              <p className="mt-0.5 text-xs text-muted-foreground">原始货号: {item.original_sku}</p>
            ) : null}
          </div>
          {(onEdit || onDelete) ? (
            <div className="flex gap-2">
              {onEdit ? (
                <Button type="button" variant="outline" size="sm" onClick={() => onEdit(item)} className="cursor-pointer">
                  编辑
                </Button>
              ) : null}
              {onDelete ? (
                <Button type="button" variant="outline" size="sm" className="text-destructive hover:text-destructive cursor-pointer" onClick={() => onDelete(item)} >
                  删除
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* Key info row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          {item.season_category ? <span><span className="text-muted-foreground">季节:</span> {item.season_category}</span> : null}
          {item.year ? <span><span className="text-muted-foreground">年份:</span> {item.year}</span> : null}
          {item.color ? <span><span className="text-muted-foreground">颜色:</span> {item.color}</span> : null}
          {item.cost ? <span><span className="text-muted-foreground">成本:</span> {item.cost}</span> : null}
          {item.size_range ? <span><span className="text-muted-foreground">尺码段:</span> {item.size_range}</span> : null}
        </div>

        {/* Grouped fields */}
        <div className="space-y-2 border-t border-border pt-2">
          {FIELD_GROUPS.map((group) => {
            const visibleFields = group.fields.filter((field) => {
              if (field === "sku" || field === "original_sku") return false
              if (field === "season_category" || field === "year" || field === "color" || field === "cost" || field === "size_range") return false
              const value = item[field as keyof ProductListItem]
              return value !== null && value !== undefined && value !== ""
            })
            if (visibleFields.length === 0) return null
            return (
              <div key={group.label}>
                <p className="mb-1 text-[11px] font-medium text-muted-foreground/70">{group.label}</p>
                <div className="grid gap-x-6 gap-y-0.5 text-xs sm:grid-cols-2 lg:grid-cols-3">
                  {visibleFields.map((field) => {
                    const value = item[field as keyof ProductListItem]
                    return (
                      <div key={field} className="flex gap-1">
                        <span className="shrink-0 text-muted-foreground">{FIELD_LABELS[field]}:</span>
                        <span className="truncate">{String(value)}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
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
  pageSizes,
  isLoading,
  error,
  onEdit,
  onDelete,
  onPageChange,
  onPageSizeChange,
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

  if (isLoading && items.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">
        正在加载商品数据...
      </div>
    )
  }

  const pageRange = buildPageRange(page, totalPages)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          共 {total} 条，当前显示 {start}-{end}
          {isLoading && items.length > 0 ? <span className="ml-2">加载中...</span> : null}
        </p>
        <div className="flex items-center gap-2">
          <span>每页</span>
          <Select
            value={String(pageSize)}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="w-25"
          >
            {pageSizes.map((size) => (
              <option key={size} value={String(size)}>{size} 条</option>
            ))}
          </Select>
        </div>
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

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  text="上一页"
                  onClick={() => onPageChange(page - 1)}
                  className={page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                />
              </PaginationItem>
              {pageRange.map((p, i) =>
                p === "ellipsis" ? (
                  <PaginationItem key={`ellipsis-${i}`}>
                    <PaginationEllipsis />
                  </PaginationItem>
                ) : (
                  <PaginationItem key={p}>
                    <PaginationLink
                      isActive={p === page}
                      onClick={() => p !== page && onPageChange(p)}
                      className={p === page ? "cursor-default" : "cursor-pointer"}
                    >
                      {p}
                    </PaginationLink>
                  </PaginationItem>
                ),
              )}
              <PaginationItem>
                <PaginationNext
                  text="下一页"
                  onClick={() => onPageChange(page + 1)}
                  className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
          <div className="flex items-center gap-1 text-sm text-muted-foreground whitespace-nowrap">
            <span>跳至</span>
            <input
              type="number"
              min={1}
              max={totalPages}
              className="h-8 w-20 rounded-md border border-input bg-background px-2 text-center text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const target = parseInt((e.target as HTMLInputElement).value, 10)
                  if (target >= 1 && target <= totalPages) {
                    onPageChange(target)
                  }
                }
              }}
            />
            <span>页</span>
          </div>
        </div>
      )}
    </div>
  )
}
