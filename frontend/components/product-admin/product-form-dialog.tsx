"use client"

import { useMemo, useState } from "react"

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
import { FIELD_GROUPS, FIELD_LABELS, ALL_PRODUCT_FIELDS } from "@/lib/fields"
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
    PAYLOAD_FIELDS.map((f) => [f, (item as Record<string, unknown>)[f] ?? ""]),
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
    payload[field] = normalize(values[field as keyof ProductFormValues] as string)
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
      <DialogContent className="max-h-[90vh] overflow-y-auto max-w-4xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <form className="space-y-6" onSubmit={handleSubmit}>
          {/* Brand + Image preview */}
          <div className="flex gap-4">
            <div className="flex-1 space-y-2">
              <Label htmlFor="product-form-brand">品牌</Label>
              <Select
                id="product-form-brand"
                value={values.brand}
                disabled={mode === "edit"}
                onChange={(event) => handleFieldChange("brand", event.target.value as BrandKey | "")}
              >
                <option value="">请选择品牌</option>
                {BRANDS.map((brand) => (
                  <option key={brand.key} value={brand.key}>
                    {brand.label}
                  </option>
                ))}
              </Select>
              {brandError ? <p className="text-sm text-destructive">{brandError}</p> : null}
            </div>

            {mode === "edit" && imageSrc ? (
              <div className="space-y-2">
                <Label>图片预览</Label>
                <img
                  src={imageSrc}
                  alt="商品图片"
                  className="h-24 w-24 rounded-lg object-contain"
                />
              </div>
            ) : null}
          </div>

          {/* Image lookup section */}
          <div className="space-y-3 rounded-lg border border-border p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium">图片匹配</p>
                <p className="text-sm text-muted-foreground">优先使用原始货号，查不到时自动回退到商品货号。</p>
              </div>
              <Button type="button" variant="outline" onClick={() => void handleLookup()} disabled={lookupDisabled}>
                {lookupStatus.status === "loading" ? "查询中..." : "查询图片"}
              </Button>
            </div>
            <ImageLookupStatus status={lookupStatus.status} message={lookupStatus.message} />
          </div>

          {/* Field groups */}
          {FIELD_GROUPS.map((group) => (
            <div key={group.label} className="space-y-3">
              <h3 className="text-sm font-medium text-muted-foreground">{group.label}</h3>
              <div className="grid gap-4 md:grid-cols-2">
                {group.fields.map((field) => (
                  <div key={field} className="space-y-2">
                    <Label htmlFor={`product-form-${field}`}>{FIELD_LABELS[field]}</Label>
                    <Input
                      id={`product-form-${field}`}
                      value={values[field as keyof ProductFormValues] as string}
                      placeholder={`请输入${FIELD_LABELS[field]}`}
                      onChange={(event) => handleFieldChange(field as keyof ProductFormValues, event.target.value)}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Image path field */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">图片路径</h3>
            <div className="space-y-2">
              <Label htmlFor="product-form-image-path">图片路径</Label>
              <Input
                id="product-form-image-path"
                value={values.image_path}
                placeholder="查询后自动填充或手动输入"
                onChange={(event) => handleFieldChange("image_path", event.target.value)}
              />
            </div>
          </div>

          {submitError ? <p className="text-sm text-destructive">{submitError}</p> : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving} className="cursor-pointer">
              取消
            </Button>
            <Button type="submit" disabled={isSaving} className="cursor-pointer">
              {isSaving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
