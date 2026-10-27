"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { X } from "lucide-react"

import { SizeGroupSelect } from "@/components/inventory-admin/size-group-select"
import { ImageLookupStatus } from "@/components/product-admin/image-lookup-status"
import { ProductOptionSelect } from "@/components/product-admin/product-option-select"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { DatePicker } from "@/components/ui/date-picker"
import { Label } from "@/components/ui/label"
import { Select } from "@/components/ui/select"
import { ApiError, createProduct, listProductAuxiliaryOptions, listProductColorBarcodes, listSizeGroupOptions, listSuppliersByBrand, lookupImage, updateProduct, type SupplierItem } from "@/lib/api"
import { PRODUCT_ARCHIVE_BRANDS, type ProductArchiveBrand, type ProductArchiveRecordBrandKey } from "@/lib/brands"
import { ALL_PRODUCT_FIELDS, BARCODE_BUILD_RULE_OPTIONS, FIELD_LABELS, SEASON_OPTIONS, getProductFieldGroups, getProductFieldLabel } from "@/lib/fields"
import type { ImageLookupStatusState, ProductAuxiliaryOptionGroup, ProductColorBarcodeItem, ProductFormValues, ProductListItem, ProductMutationPayload, SizeGroup } from "@/lib/types"
import { cn } from "@/lib/utils"

type ProductFormDialogProps = {
  brands?: readonly ProductArchiveBrand[]
  item?: ProductListItem | null
  mode: "create" | "edit"
  onOpenChange: (open: boolean) => void
  onSaved: () => void | Promise<void>
  open: boolean
}

const PAYLOAD_FIELDS = [...ALL_PRODUCT_FIELDS, "image_path"] as const
const AUXILIARY_OPTION_FIELDS = new Set([
  "product_name",
  "product_model",
  "upper_material",
  "lining_material",
  "outsole_material",
  "insole_material",
  "execution_standard",
])

function makeEmptyForm(): Record<string, string> {
  return Object.fromEntries(PAYLOAD_FIELDS.map((f) => [f, ""]))
}

const EMPTY_FORM: ProductFormValues = { brand: "", ...makeEmptyForm() } as ProductFormValues

function colorNameVariants(value: string) {
  const normalized = value.trim()
  if (!normalized) return new Set<string>()
  const withoutBrandSuffix = normalized.replace(/\s*[（(]\s*笑脸\s*[）)]\s*$/u, "").trim()
  const baseNames = new Set([normalized, withoutBrandSuffix].filter(Boolean))
  const variants = new Set<string>()
  baseNames.forEach((baseName) => {
    variants.add(baseName)
    variants.add(baseName.endsWith("色") ? baseName.slice(0, -1) : `${baseName}色`)
  })
  return variants
}

function findUniqueColorCode(colorName: string, options: ProductColorBarcodeItem[]) {
  const targetNames = colorNameVariants(colorName)
  if (targetNames.size === 0) return ""
  const codes = new Set(
    options
      .filter((option) => Array.from(colorNameVariants(option.color_name)).some((name) => targetNames.has(name)))
      .map((option) => option.color_code),
  )
  return codes.size === 1 ? Array.from(codes)[0] : ""
}

type ColorCodeSearchSelectProps = {
  allowCustomValue?: boolean
  disabled: boolean
  id: string
  isLoading: boolean
  onChange: (value: string) => void
  options: ProductColorBarcodeItem[]
  value: string
}

function ColorCodeSearchSelect({ allowCustomValue = false, disabled, id, isLoading, onChange, options, value }: ColorCodeSearchSelectProps) {
  const selectOptions = useMemo(() => options.map((option) => ({
    value: option.color_code,
    label: option.color_code,
    description: option.color_name,
  })), [options])

  return (
    <ProductOptionSelect
      id={id}
      label="颜色代码"
      value={value}
      options={selectOptions}
      onValueChange={onChange}
      allowCustomValue={allowCustomValue}
      disabled={disabled}
      isLoading={isLoading}
      placeholder="搜索颜色代码/颜色名称"
      emptyText="没有匹配的颜色代码"
    />
  )
}

type SupplierSearchSelectProps = {
  disabled: boolean
  id: string
  isLoading: boolean
  onChange: (value: string) => void
  options: SupplierItem[]
  value: string
}

type AuxiliaryAttributeSelectProps = {
  disabled: boolean
  id: string
  label: string
  onChange: (value: string) => void
  options: string[]
  value: string
}

function AuxiliaryAttributeSelect({ disabled, id, label, onChange, options, value }: AuxiliaryAttributeSelectProps) {
  const selectOptions = useMemo(() => options.map((option) => ({ value: option, label: option })), [options])
  return (
    <ProductOptionSelect
      id={id}
      label={label}
      value={value}
      options={selectOptions}
      onValueChange={onChange}
      disabled={disabled}
      isLoading={disabled}
      emptyText="没有匹配的辅助属性"
    />
  )
}

function SupplierSearchSelect({ disabled, id, isLoading, onChange, options, value }: SupplierSearchSelectProps) {
  const selectOptions = useMemo(() => options.map((option) => ({
    value: option.name,
    label: option.name,
    keywords: option.factory_code || "",
  })), [options])
  return (
    <ProductOptionSelect
      id={id}
      label="供应商"
      value={value}
      options={selectOptions}
      onValueChange={onChange}
      disabled={disabled}
      isLoading={isLoading}
      placeholder="搜索供应商/工厂代码"
      emptyText="该品牌暂无匹配供应商"
    />
  )
}

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

  if (item.brand === "smiley" && item.sku && (!item.color_code || item.color_code === item.sku)) {
    base.color_code = item.sku.trim().slice(-4)
  }

  return {
    brand: item.brand as ProductArchiveRecordBrandKey,
    ...base,
  } as ProductFormValues
}

function toPayload(values: ProductFormValues): ProductMutationPayload {
  const normalize = (value: string) => {
    const trimmed = value.trim()
    return trimmed.length > 0 ? trimmed : null
  }

  const payload: Record<string, unknown> = {}
  const payloadFields = [
    ...getProductFieldGroups(values.brand).flatMap((group) => group.fields),
    "image_path",
  ]
  for (const field of payloadFields) {
    const value = values[field as keyof ProductFormValues]
    if (typeof value === "string") {
      payload[field] = normalize(value)
    } else {
      payload[field] = value ?? null
    }
  }

  return payload as ProductMutationPayload
}

export function ProductFormDialog({ brands = PRODUCT_ARCHIVE_BRANDS, item, mode, onOpenChange, onSaved, open }: ProductFormDialogProps) {
  const initialValues = useMemo(() => toFormValues(item), [item])
  const [values, setValues] = useState<ProductFormValues>(initialValues)
  const [brandError, setBrandError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [lookupStatus, setLookupStatus] = useState<ImageLookupStatusState>({ status: "idle", message: null })
  const [colorBarcodeOptions, setColorBarcodeOptions] = useState<ProductColorBarcodeItem[]>([])
  const [isLoadingColorBarcodes, setIsLoadingColorBarcodes] = useState(false)
  const [supplierOptions, setSupplierOptions] = useState<SupplierItem[]>([])
  const [isLoadingSuppliers, setIsLoadingSuppliers] = useState(false)
  const autoMatchedColorCodeRef = useRef("")
  const manuallyEditedSmileyCodeRef = useRef(false)
  const [sizeGroups, setSizeGroups] = useState<SizeGroup[]>([])
  const [isLoadingSizeGroups, setIsLoadingSizeGroups] = useState(false)
  const [auxiliaryOptionState, setAuxiliaryOptionState] = useState<{
    brand: string
    items: ProductAuxiliaryOptionGroup[]
  }>({ brand: "", items: [] })

  const auxiliaryOptionsByField = useMemo(
    () => new Map(
      auxiliaryOptionState.brand === values.brand
        ? auxiliaryOptionState.items.map((group) => [group.field, group.options] as const)
        : [],
    ),
    [auxiliaryOptionState, values.brand],
  )
  const isLoadingAuxiliaryOptions = Boolean(values.brand && auxiliaryOptionState.brand !== values.brand)

  const title = mode === "create" ? "新增商品" : "编辑商品"
  const lookupDisabled = useMemo(() => {
    return !values.brand || (!values.original_sku.trim() && !values.sku.trim()) || lookupStatus.status === "loading"
  }, [lookupStatus.status, values.brand, values.original_sku, values.sku])

  useEffect(() => {
    setValues(initialValues)
    autoMatchedColorCodeRef.current = ""
    manuallyEditedSmileyCodeRef.current = Boolean(
      item?.brand === "smiley" && item.color_code && item.color_code !== item.sku?.trim().slice(-4) && item.color_code !== item.sku,
    )
    setLookupStatus({ status: "idle", message: null })
    setSubmitError(null)
    setBrandError(null)
  }, [initialValues, item, open])

  useEffect(() => {
    if (!open || !values.brand) {
      setColorBarcodeOptions([])
      return
    }

    if (values.brand === "ni" || values.brand === "ns") {
      setColorBarcodeOptions([])
      setIsLoadingColorBarcodes(false)
      return
    }

    let cancelled = false
    setIsLoadingColorBarcodes(true)

    listProductColorBarcodes(values.brand)
      .then((response) => {
        if (!cancelled) {
          setColorBarcodeOptions(response.items)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setColorBarcodeOptions([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingColorBarcodes(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [open, values.brand])

  useEffect(() => {
    if (!open || !values.brand) {
      setSupplierOptions([])
      setIsLoadingSuppliers(false)
      return
    }

    let cancelled = false
    setIsLoadingSuppliers(true)
    listSuppliersByBrand(values.brand)
      .then((response) => {
        if (!cancelled) setSupplierOptions(response.items)
      })
      .catch(() => {
        if (!cancelled) setSupplierOptions([])
      })
      .finally(() => {
        if (!cancelled) setIsLoadingSuppliers(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, values.brand])

  useEffect(() => {
    if (!open || !values.brand) return

    let cancelled = false
    listProductAuxiliaryOptions(values.brand)
      .then((response) => {
        if (!cancelled) setAuxiliaryOptionState({ brand: response.brand, items: response.items })
      })
      .catch(() => {
        if (!cancelled) setAuxiliaryOptionState({ brand: values.brand, items: [] })
      })

    return () => {
      cancelled = true
    }
  }, [open, values.brand])

  useEffect(() => {
    if (!open || values.brand === "smiley" || values.brand === "ns" || values.color_code.trim()) return
    const colorCode = findUniqueColorCode(values.color, colorBarcodeOptions)
    if (!colorCode) return
    autoMatchedColorCodeRef.current = colorCode
    setValues((current) => (
      current.color_code.trim() || current.color.trim() !== values.color.trim()
        ? current
        : { ...current, color_code: colorCode }
    ))
  }, [colorBarcodeOptions, open, values.brand, values.color, values.color_code])

  useEffect(() => {
    if (!open || values.brand !== "smiley" || !values.color_code.trim()) return
    const matched = colorBarcodeOptions.find((option) => option.color_code === values.color_code.trim())
    if (matched && values.color !== matched.color_name) {
      setValues((current) => current.color_code.trim() === matched.color_code
        ? { ...current, color: matched.color_name }
        : current)
    }
  }, [colorBarcodeOptions, open, values.brand, values.color, values.color_code])

  useEffect(() => {
    if (!open) return

    let cancelled = false
    setIsLoadingSizeGroups(true)
    listSizeGroupOptions()
      .then((response) => {
        if (!cancelled) {
          setSizeGroups(response.items)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSizeGroups([])
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingSizeGroups(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [open])

  const handleFieldChange = (field: keyof ProductFormValues, nextValue: string) => {
    if (field === "color") {
      if (values.brand === "smiley" || values.brand === "ns") {
        setValues((current) => ({ ...current, color: nextValue }))
        return
      }
      const currentColorCode = values.color_code.trim()
      const canReplaceColorCode = !currentColorCode || currentColorCode === autoMatchedColorCodeRef.current
      const matchedColorCode = canReplaceColorCode ? findUniqueColorCode(nextValue, colorBarcodeOptions) : currentColorCode
      autoMatchedColorCodeRef.current = canReplaceColorCode ? matchedColorCode : ""
      setValues((current) => ({
        ...current,
        color: nextValue,
        ...(canReplaceColorCode ? { color_code: matchedColorCode } : {}),
      }))
      return
    }

    if (field === "brand") {
      const shouldClearAutoMatchedCode = values.color_code.trim() === autoMatchedColorCodeRef.current
      autoMatchedColorCodeRef.current = ""
      manuallyEditedSmileyCodeRef.current = false
      setValues((current) => ({
        ...current,
        brand: nextValue as ProductArchiveRecordBrandKey | "",
        ...(shouldClearAutoMatchedCode ? { color_code: "" } : {}),
        ...(nextValue === "smiley" ? { color_code: current.sku.trim().slice(-4) } : {}),
        ...(current.brand !== nextValue ? { supplier_name: "" } : {}),
      }))
      setBrandError(null)
      return
    }

    setValues((current) => ({
      ...current,
      [field]: nextValue,
      ...(field === "sku" && current.brand === "smiley" && !manuallyEditedSmileyCodeRef.current
        ? { color_code: nextValue.trim().slice(-4) }
        : {}),
    }))

    if (field === "original_sku" || field === "sku") {
      setLookupStatus({ status: "idle", message: null })
    }
  }

  const handleColorCodeChange = (nextValue: string) => {
    const selected = colorBarcodeOptions.find((option) => option.color_code === nextValue)
    autoMatchedColorCodeRef.current = ""
    if (values.brand === "smiley") manuallyEditedSmileyCodeRef.current = true
    setValues((current) => ({
      ...current,
      color_code: nextValue,
      color: selected?.color_name ?? (current.brand === "smiley" ? "" : current.color),
    }))
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
      if (error instanceof ApiError && error.status >= 500) {
        setLookupStatus({
          status: "warning",
          message: "未找到对应图片，或图片目录暂时不可用，可继续保存商品。",
        })
        return
      }

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
      if (finalValues.brand === "smiley" && !finalValues.color_code.trim()) {
        finalValues.color_code = finalValues.sku.trim().slice(-4)
      }

      const payload = toPayload(finalValues)

      if (mode === "create") {
        await createProduct(values.brand, payload)
      } else if (item) {
        await updateProduct(item.brand as ProductArchiveRecordBrandKey, item.id, payload)
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
                    onChange={(event) => handleFieldChange("brand", event.target.value as ProductArchiveRecordBrandKey | "")}
                    autoComplete="off"
                  >
                    <option value="">请选择品牌</option>
                    {brands.filter((brand) => brand.key !== "all").map((brand) => (
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

                {getProductFieldGroups(values.brand).map((group) => {
                  const fields = group.fields.filter((f) => f !== "sku" && f !== "original_sku")
                  return (
                    <div key={group.label}>
                      <p className="mb-2 text-xs font-medium text-muted-foreground">{group.label}</p>
                      <div className={cn("grid gap-4 md:grid-cols-2", group.label !== "物价信息" && "lg:grid-cols-3")}>
                        {fields.map((field) => (
                          <div key={field} className="space-y-1.5">
                            <Label htmlFor={`product-form-${field}`} className="text-xs">{getProductFieldLabel(field, values.brand)}</Label>
                            {(isLoadingAuxiliaryOptions && AUXILIARY_OPTION_FIELDS.has(field)) || auxiliaryOptionsByField.has(field) ? (
                              <AuxiliaryAttributeSelect
                                id={`product-form-${field}`}
                                label={getProductFieldLabel(field, values.brand)}
                                value={values[field as keyof ProductFormValues] as string}
                                disabled={isLoadingAuxiliaryOptions}
                                options={auxiliaryOptionsByField.get(field) ?? []}
                                onChange={(nextValue) => handleFieldChange(field as keyof ProductFormValues, nextValue)}
                              />
                            ) : field === "season_category" ? (
                              <ProductOptionSelect
                                id={`product-form-${field}`}
                                label={getProductFieldLabel(field, values.brand)}
                                value={values[field as keyof ProductFormValues] as string}
                                options={SEASON_OPTIONS.map((option) => ({ value: option, label: option }))}
                                onValueChange={(nextValue) => handleFieldChange(field as keyof ProductFormValues, nextValue)}
                                placeholder="请选择季节"
                              />
                            ) : field === "barcode_build_rule" ? (
                              <ProductOptionSelect
                                id={`product-form-${field}`}
                                label={getProductFieldLabel(field, values.brand)}
                                value={values.barcode_build_rule}
                                options={BARCODE_BUILD_RULE_OPTIONS.map((option) => ({ value: option, label: option }))}
                                onValueChange={(nextValue) => handleFieldChange("barcode_build_rule", nextValue)}
                                placeholder="请选择条码构成逻辑"
                              />
                            ) : field === "size_range" ? (
                              <SizeGroupSelect
                                id={`product-form-${field}`}
                                value={values.size_range}
                                groups={sizeGroups}
                                disabled={isLoadingSizeGroups}
                                onValueChange={(nextValue) => handleFieldChange("size_range", nextValue)}
                              />
                            ) : field === "supplier_name" ? (
                              <SupplierSearchSelect
                                id={`product-form-${field}`}
                                value={values.supplier_name}
                                options={supplierOptions}
                                isLoading={isLoadingSuppliers}
                                disabled={!values.brand || isLoadingSuppliers}
                                onChange={(nextValue) => handleFieldChange("supplier_name", nextValue)}
                              />
                            ) : field === "first_order_time" || field === "launch_date" ? (
                              <DatePicker
                                id={`product-form-${field}`}
                                value={values[field as keyof ProductFormValues] as string}
                                onValueChange={(nextDate) => handleFieldChange(field as keyof ProductFormValues, nextDate)}
                                autoComplete="off"
                              />
                            ) : field === "color_code" && values.brand !== "ns" ? (
                              <ColorCodeSearchSelect
                                id={`product-form-${field}`}
                                value={values.color_code}
                                options={colorBarcodeOptions}
                                isLoading={isLoadingColorBarcodes}
                                disabled={!values.brand || isLoadingColorBarcodes}
                                allowCustomValue={values.brand === "smiley"}
                                onChange={handleColorCodeChange}
                              />
                            ) : (
                              <Input
                                id={`product-form-${field}`}
                                value={values[field as keyof ProductFormValues] as string}
                                placeholder={`请输入${getProductFieldLabel(field, values.brand)}`}
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
                  <p className="mb-2 text-xs font-medium text-muted-foreground">图片存储</p>
                  <div className="space-y-1.5">
                    <Label htmlFor="product-form-image-path" className="text-xs">图片路径</Label>
                    <Input
                      id="product-form-image-path"
                      value={item?.image_storage_path ?? ""}
                      placeholder={values.image_path ? "等待同步到 US3" : "暂无图片"}
                      readOnly
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
