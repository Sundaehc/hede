import {
  ImageOff,
  Layers3,
  Package,
  Ruler,
  Shapes,
  Tags,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { PRODUCT_ARCHIVE_BRANDS, type ProductArchiveBrand } from "@/lib/brands"
import { getProductFieldGroups, getProductFieldLabel } from "@/lib/fields"
import type { ProductListItem } from "@/lib/types"
import { cn } from "@/lib/utils"

const SECTION_ICONS = {
  基础信息: Package,
  材质信息: Layers3,
  女鞋款式信息: Shapes,
  尺寸信息: Ruler,
  其他: Tags,
  笑脸商品信息: Tags,
}

const FULL_WIDTH_FIELDS = new Set([
  "product_name",
  "selling_points",
  "internal_height_note",
])
const CODE_FIELDS = new Set([
  "original_sku",
  "sku",
  "factory_sku",
  "color_code",
  "factory_code",
  "barcode",
])

type ProductDetailDialogProps = {
  item: ProductListItem
  brands?: readonly ProductArchiveBrand[]
  showCost?: boolean
  onClose: () => void
}

function productDetailValue(
  item: ProductListItem,
  field: keyof ProductListItem
) {
  if (field === "cost" && item.gender_costs?.female && item.gender_costs.male) {
    return `女码 ${item.gender_costs.female} / 男码 ${item.gender_costs.male}`
  }
  const value = item[field]
  return value === null || value === undefined || value === ""
    ? "—"
    : String(value)
}

export function ProductDetailDialog({
  item,
  brands = PRODUCT_ARCHIVE_BRANDS,
  showCost = false,
  onClose,
}: ProductDetailDialogProps) {
  const brandLabel =
    brands.find((brand) => brand.key === item.brand)?.label ?? item.brand
  const fieldGroups: {
    label: string
    fields: { field: keyof ProductListItem; label: string }[]
  }[] = getProductFieldGroups(item.brand).map((group) => ({
    label: group.label,
    fields: group.fields
      .filter((field) => showCost || field !== "cost")
      .map((field) => ({
        field,
        label: getProductFieldLabel(field, item.brand),
      })),
  }))
  if (item.brand === "smiley") {
    fieldGroups.push({
      label: "笑脸商品信息",
      fields: [
        { field: "factory_code", label: "工厂代码" },
        { field: "market_price", label: "市场价" },
        { field: "barcode", label: "商品条码" },
        { field: "accessories", label: "配件" },
      ],
    })
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-h-[92svh] max-w-6xl overflow-hidden rounded-2xl bg-card p-0 shadow-2xl">
        <div className="flex max-h-[92svh] flex-col">
          <DialogHeader className="flex shrink-0 flex-row items-center justify-between gap-4 space-y-0 border-b border-border/70 px-4 py-3.5 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <span
                className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-muted/60"
                aria-hidden="true"
              >
                <Package className="size-4 text-foreground/75" />
              </span>
              <DialogTitle className="min-w-0 text-base font-semibold tracking-normal">
                商品详情
              </DialogTitle>
              <span
                className="hidden h-4 w-px bg-border sm:block"
                aria-hidden="true"
              />
              <span
                className="hidden truncate font-mono text-xs text-muted-foreground sm:block"
                title={item.sku || item.original_sku || undefined}
              >
                {item.sku || item.original_sku || "—"}
              </span>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label="关闭商品详情"
              className="size-8 shrink-0 cursor-pointer rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </Button>
          </DialogHeader>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-muted/25 p-3 [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin] sm:p-5">
            <div className="grid items-start gap-4 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-5 xl:grid-cols-[240px_minmax(0,1fr)]">
              <div className="grid min-w-0 grid-cols-[104px_minmax(0,1fr)] items-center gap-4 rounded-xl border border-border/70 bg-card p-3 shadow-xs sm:grid-cols-[140px_minmax(0,1fr)] lg:sticky lg:top-0 lg:flex lg:flex-col lg:items-stretch lg:gap-0 lg:p-0">
                <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-lg bg-muted/35 p-2 lg:rounded-t-xl lg:rounded-b-none lg:border-b lg:border-border/60 lg:p-4">
                  {item.image_url ? (
                    <img
                      src={`/api${item.image_url}`}
                      alt={item.sku || item.original_sku || "商品图片"}
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-2 text-muted-foreground/60">
                      <ImageOff
                        className="size-7 stroke-[1.25]"
                        aria-hidden="true"
                      />
                      <span className="text-xs">暂无图片</span>
                    </div>
                  )}
                </div>
                <div className="min-w-0 space-y-2.5 lg:p-4">
                  <span className="inline-flex max-w-full rounded-md border border-border/70 bg-muted/60 px-2 py-1 text-[11px] font-medium text-muted-foreground">
                    {brandLabel}
                  </span>
                  <p className="text-base leading-snug font-semibold tracking-tight break-words">
                    {item.product_name ||
                      item.sku ||
                      item.original_sku ||
                      "商品资料"}
                  </p>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    {[item.year, item.season_category, item.color]
                      .filter(Boolean)
                      .map((value, index) => (
                        <span
                          key={index}
                          className="inline-flex items-center gap-2"
                        >
                          {index > 0 ? (
                            <span
                              className="size-0.5 rounded-full bg-muted-foreground/45"
                              aria-hidden="true"
                            />
                          ) : null}
                          {value}
                        </span>
                      ))}
                  </p>
                </div>
              </div>

              <div className="min-w-0 space-y-3.5">
                {fieldGroups.map((group) => {
                  const SectionIcon =
                    SECTION_ICONS[group.label as keyof typeof SECTION_ICONS] ??
                    Tags
                  return (
                    <section
                      key={group.label}
                      className="overflow-hidden rounded-xl border border-border/70 bg-card shadow-xs"
                    >
                      <div className="flex items-center gap-2.5 border-b border-border/60 bg-muted/35 px-4 py-2.5">
                        <SectionIcon
                          className="size-3.5 text-muted-foreground"
                          aria-hidden="true"
                        />
                        <h3 className="text-[13px] font-semibold tracking-wide">
                          {group.label}
                        </h3>
                      </div>
                      <dl className="flex flex-wrap gap-px bg-border/50">
                        {group.fields.map(({ field, label }) => {
                          const value = productDetailValue(item, field)
                          const isEmpty = value === "—"
                          return (
                            <div
                              key={field}
                              className={cn(
                                "grid min-w-0 flex-[1_1_100%] grid-cols-[88px_minmax(0,1fr)] items-start gap-3 bg-card px-4 py-2.5 transition-colors hover:bg-muted/25 sm:flex-[1_1_calc(50%-0.5px)]",
                                FULL_WIDTH_FIELDS.has(field) && "sm:basis-full"
                              )}
                            >
                              <dt className="pt-0.5 text-xs leading-5 text-muted-foreground">
                                {label}
                              </dt>
                              <dd
                                className={cn(
                                  "min-w-0 text-[13px] leading-6 [overflow-wrap:anywhere] whitespace-pre-wrap",
                                  isEmpty
                                    ? "text-muted-foreground/45"
                                    : "font-medium text-foreground/90",
                                  CODE_FIELDS.has(field) &&
                                    !isEmpty &&
                                    "font-mono text-[12px] tracking-wide"
                                )}
                              >
                                {value}
                              </dd>
                            </div>
                          )
                        })}
                      </dl>
                    </section>
                  )
                })}
                <dl className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-3">
                  <dt className="mb-1.5 text-[11px] font-medium text-muted-foreground">
                    图片路径
                  </dt>
                  <dd className="font-mono text-[11px] leading-5 break-all text-muted-foreground/80">
                    {item.image_storage_path ||
                      (item.image_path ? "等待同步到 US3" : "暂无图片")}
                  </dd>
                </dl>
              </div>
            </div>
          </div>

          <DialogFooter className="shrink-0 border-t border-border/70 bg-card px-4 py-3 sm:px-6">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              className="min-w-20 cursor-pointer rounded-lg"
            >
              关闭
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}
