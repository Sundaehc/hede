"use client"

import { useMemo, useState } from "react"
import { X } from "lucide-react"

import { ImageLookupStatus } from "@/components/product-admin/image-lookup-status"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { ApiError, createProduct, lookupImage, updateProduct } from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import { ALL_PRODUCT_FIELDS, FIELD_GROUPS, FIELD_LABELS, SEASON_OPTIONS } from "@/lib/fields"
import type { ImageLookupStatusState, ProductFormValues, ProductListItem, ProductMutationPayload } from "@/lib/types"

type ProductFormDialogProps = {
  item?: ProductListItem | null
  mode: "create" | "edit"
  onOpenChange: (open: boolean) => void
  onSaved: () => void | Promise<void>
  open: boolean
}

const PAYLOAD_FIELDS = [...ALL_PRODUCT_FIELDS, "image_path"] as const

function makeEmptyForm(): Record<string, string> {
  return Object.fromEntries(PAYLOAD_FIELDS.map((f) => [f, ""]))
}

const EMPTY_FORM: ProductFormValues = { brand: "", ...makeEmptyForm() } as ProductFormValues

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message || `请求失败（${error.status}）`
  }

  if (error instanceof Error) {
    return error.message
  }

  return "操作失败，请稍后重试"
}

function toFormValues(item?: ProductListItem | null): ProductFormValues {
  if (!item) {
    return EMPTY_FORM
  }

  const base = Object.fromEntries(
    PAYLOAD_FIELDS.map((f) => {
      const raw = (item as Record<string, unknown>)[f]
      if (raw == null) return [f, ""]
      if (typeof raw === "object") return [f, raw]
      return [f, String(raw)]
    }),
  )

  return {
    brand: item.brand,
    ...base,
  } as ProductFormValues
}

function toPayload(values: ProductFormValues): ProductMutationPayload {
  const normalize = (value: string) => {
    const trimmed = value.trim()
    return trimmed.length > 0 ? trimmed : null
  }

  const payload: Record<string, unknown> = {}
  for (const field of PAYLOAD_FIELDS) {
    const value = values[field as keyof ProductFormValues]
    if (typeof value === "string") {
      payload[field] = normalize(value)
    } else {
      payload[field] = value ?? null
    }
  }

  return payload as ProductMutationPayload
}

export function ProductFormDialog({ item, mode, onOpenChange, onSaved, open }: ProductFormDialogProps) {
  const initialValues = useMemo(() => toFormValues(item), [item])
  const [values, setValues] = useState<ProductFormValues>(initialValues)
  const [brandError, setBrandError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [lookupStatus, setLookupStatus] = useState<ImageLookupStatusState>({ status: "idle", message: null })

  const title = mode === "create" ? "新增商品" : "编辑商品"
  const lookupDisabled = useMemo(() => {
    return !values.brand || (!values.original_sku.trim() && !values.sku.trim()) || lookupStatus.status === "loading"
  }, [lookupStatus.status, values.brand, values.original_sku, values.sku])

  const handleFieldChange = (field: keyof ProductFormValues, nextValue: string) => {
    setValues((current) => ({ ...current, [field]: nextValue }))

    if (field === "brand") {
      setBrandError(null)
    }

    if (field === "original_sku" || field === "sku") {
      setLookupStatus({ status: "idle", message: null })
    }
  }

  const handleLookup = async () => {
    if (!values.brand) {
      setBrandError("请选择品牌")
      return
    }

    setBrandError(null)
    setLookupStatus({ status: "loading", message: "正在查询商品图片..." })

    try {
      const result = await lookupImage({
        brand: values.brand,
        originalSku: values.original_sku.trim() || null,
        sku: values.sku.trim() || null,
      })

      if (result.found && result.image_path) {
        setValues((current) => ({ ...current, image_path: result.image_path ?? "" }))
        setLookupStatus({
          status: "success",
          message: result.message || `已通过${result.matched_by === "original_sku" ? "原始货号" : "商品货号"}匹配图片。`,
        })
        return
      }

      setLookupStatus({
        status: "warning",
        message: result.message || "未找到对应图片，可继续保存商品。",
      })
    } catch (error) {
      setLookupStatus({
        status: "error",
        message: getErrorMessage(error),
      })
    }
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitError(null)

    if (!values.brand) {
      setBrandError("请选择品牌")
      return
    }

    setBrandError(null)
    setIsSaving(true)

    try {
      const finalValues = { ...values }
      if (finalValues.original_sku.trim() && !finalValues.sku.trim()) {
        finalValues.sku = finalValues.original_sku
      }

      const payload = toPayload(finalValues)

      if (mode === "create") {
        await createProduct(values.brand, payload)
      } else if (item) {
        await updateProduct(item.brand, item.id, payload)
      }

      await onSaved()
      onOpenChange(false)
    } catch (error) {
      setSubmitError(getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  const imageSrc = item?.image_url ? `/api${item.image_url}` : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-hidden p-0">
        <div className="flex max-h-[90vh] flex-col">
          <DialogHeader className="flex flex-row items-center justify-between gap-4 border-b border-border px-6 py-4 space-y-0">
            <DialogTitle className="min-w-0 truncate">{title}</DialogTitle>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 cursor-pointer"
              onClick={() => onOpenChange(false)}
              aria-label="关闭编辑弹窗"
            >
              <X className="h-4 w-4" />
            </Button>
          </DialogHeader>

          <form id="product-form" className="min-h-0 flex-1 overflow-y-auto px-6 py-5" onSubmit={handleSubmit}>
            <div className="grid gap-6 lg:grid-cols-[232px_minmax(0,1fr)]">
              <div className="flex flex-col gap-3 lg:sticky lg:top-0 lg:self-start">
                <div className="space-y-2">
                  <Label htmlFor="product-form-brand">品牌</Label>
                  <Select
                    id="product-form-brand"
                    value={values.brand}
                    disabled={mode === "edit"}
                    onChange={(event) => handleFieldChange("brand", event.target.value as BrandKey | "")}
                    autoComplete="off"
                  >
                    <option value="">请选择品牌</option>
                    {BRANDS.filter((b) => b.key !== "all").map((brand) => (
                      <option key={brand.key} value={brand.key}>
                        {brand.label}
                      </option>
                    ))}
                  </Select>
                  {brandError ? <p className="text-sm text-destructive">{brandError}</p> : null}
                </div>

                {imageSrc ? (
                  <div className="space-y-2">
                    <Label>图片预览</Label>
                    <img
                      src={imageSrc}
                      alt="商品图片"
                      className="aspect-square w-full max-w-[11rem] rounded-lg border border-border object-contain"
                    />
                  </div>
                ) : (
                  <div className="flex aspect-square w-full max-w-[11rem] items-center justify-center rounded-lg border border-border bg-muted text-xs text-muted-foreground">
                    暂无图片
                  </div>
                )}

                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground">优先原始货号，查不到回退商品货号</p>
                  <Button type="button" variant="outline" size="sm" onClick={() => void handleLookup()} disabled={lookupDisabled} className="w-full cursor-pointer">
                    {lookupStatus.status === "loading" ? "查询中..." : "查询图片"}
                  </Button>
                  <ImageLookupStatus status={lookupStatus.status} message={lookupStatus.message} />
                </div>
              </div>

              <div className="min-w-0 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="product-form-sku">{FIELD_LABELS.sku}</Label>
                    <Input
                      id="product-form-sku"
                      value={values.sku}
                      placeholder={`请输入${FIELD_LABELS.sku}`}
                      onChange={(event) => handleFieldChange("sku", event.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="product-form-original_sku">{FIELD_LABELS.original_sku}</Label>
                    <Input
                      id="product-form-original_sku"
                      value={values.original_sku}
                      placeholder={`请输入${FIELD_LABELS.original_sku}`}
                      onChange={(event) => handleFieldChange("original_sku", event.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                </div>

                {FIELD_GROUPS.map((group) => {
                  const fields = group.fields.filter((f) => f !== "sku" && f !== "original_sku")
                  return (
                    <div key={group.label}>
                      <p className="mb-2 text-xs font-medium text-muted-foreground">{group.label}</p>
                      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {fields.map((field) => (
                          <div key={field} className="space-y-1.5">
                            <Label htmlFor={`product-form-${field}`} className="text-xs">{FIELD_LABELS[field]}</Label>
                            {field === "season_category" ? (
                              <Select
                                id={`product-form-${field}`}
                                value={values[field as keyof ProductFormValues] as string}
                                onChange={(event) => handleFieldChange(field as keyof ProductFormValues, event.target.value)}
                                autoComplete="off"
                              >
                                <option value="">请选择</option>
                                {SEASON_OPTIONS.map((opt) => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </Select>
                            ) : field === "first_order_time" || field === "launch_date" ? (
                              <Input
                                id={`product-form-${field}`}
                                type="date"
                                value={values[field as keyof ProductFormValues] as string}
                                onChange={(event) => handleFieldChange(field as keyof ProductFormValues, event.target.value)}
                                autoComplete="off"
                              />
                            ) : (
                              <Input
                                id={`product-form-${field}`}
                                value={values[field as keyof ProductFormValues] as string}
                                placeholder={`请输入${FIELD_LABELS[field]}`}
                                onChange={(event) => handleFieldChange(field as keyof ProductFormValues, event.target.value)}
                                autoComplete="off"
                                spellCheck={false}
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}

                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">图片路径</p>
                  <div className="space-y-1.5">
                    <Label htmlFor="product-form-image-path" className="text-xs">{FIELD_LABELS.image_path}</Label>
                    <Input
                      id="product-form-image-path"
                      value={values.image_path}
                      placeholder="查询后自动填充或手动输入"
                      onChange={(event) => handleFieldChange("image_path", event.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                </div>

                {submitError ? <p className="text-sm text-destructive">{submitError}</p> : null}
              </div>
            </div>
          </form>

          <DialogFooter className="border-t border-border bg-background/95 px-6 py-4 backdrop-blur">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving} className="cursor-pointer">
              取消
            </Button>
            <Button type="submit" form="product-form" disabled={isSaving} className="cursor-pointer">
              {isSaving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}
