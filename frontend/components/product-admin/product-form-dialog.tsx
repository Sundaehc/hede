"use client"

import { useEffect, useId, useMemo, useRef, useState } from "react"
import { Check, Search, X } from "lucide-react"

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
import { ApiError, createProduct, listProductColorBarcodes, lookupImage, updateProduct } from "@/lib/api"
import { BRANDS, type BrandKey } from "@/lib/brands"
import { ALL_PRODUCT_FIELDS, FIELD_GROUPS, FIELD_LABELS, SEASON_OPTIONS } from "@/lib/fields"
import type { ImageLookupStatusState, ProductColorBarcodeItem, ProductFormValues, ProductListItem, ProductMutationPayload } from "@/lib/types"
import { cn } from "@/lib/utils"

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

type ColorCodeSearchSelectProps = {
  disabled: boolean
  id: string
  isLoading: boolean
  onChange: (value: string) => void
  options: ProductColorBarcodeItem[]
  value: string
}

function ColorCodeSearchSelect({ disabled, id, isLoading, onChange, options, value }: ColorCodeSearchSelectProps) {
  const listboxId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState("")

  const selected = options.find((option) => option.color_code === value)
  const displayValue = selected ? `${selected.color_code} - ${selected.color_name}` : value
  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) {
      return options
    }

    return options.filter((option) => {
      return `${option.color_code} ${option.color_name}`.toLowerCase().includes(normalizedQuery)
    })
  }, [options, query])
  const visibleOptions = filteredOptions.slice(0, 80)

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      if (rootRef.current?.contains(event.target as Node)) {
        return
      }

      setIsOpen(false)
      setQuery("")
    }

    document.addEventListener("mousedown", handlePointerDown)
    document.addEventListener("touchstart", handlePointerDown)

    return () => {
      document.removeEventListener("mousedown", handlePointerDown)
      document.removeEventListener("touchstart", handlePointerDown)
    }
  }, [isOpen])

  const handleSelect = (nextValue: string) => {
    onChange(nextValue)
    setQuery("")
    setIsOpen(false)
    inputRef.current?.blur()
  }

  return (
    <div ref={rootRef} className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        id={id}
        ref={inputRef}
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-autocomplete="list"
        value={isOpen ? query : displayValue}
        placeholder={isLoading ? "颜色代码加载中..." : "搜索颜色代码/颜色名称"}
        disabled={disabled}
        onFocus={() => {
          if (disabled) return
          setQuery("")
          setIsOpen(true)
        }}
        onChange={(event) => {
          setQuery(event.target.value)
          setIsOpen(true)
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setIsOpen(false)
            setQuery("")
            inputRef.current?.blur()
            return
          }

          if (event.key === "Enter" && isOpen && visibleOptions.length > 0) {
            event.preventDefault()
            handleSelect(visibleOptions[0].color_code)
          }
        }}
        className="pl-8"
        autoComplete="off"
        spellCheck={false}
      />

      {isOpen ? (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-50 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border bg-popover py-1 text-sm shadow-lg"
        >
          {visibleOptions.length > 0 ? (
            visibleOptions.map((option) => {
              const isSelected = option.color_code === value
              return (
                <button
                  key={`${option.brand}-${option.color_code}-${option.color_name}`}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted focus-visible:bg-muted focus-visible:outline-none",
                    isSelected && "bg-muted",
                  )}
                  onMouseDown={(event) => {
                    event.preventDefault()
                    handleSelect(option.color_code)
                  }}
                >
                  <span className="shrink-0 font-medium text-foreground">{option.color_code}</span>
                  <span className="min-w-0 truncate text-muted-foreground">{option.color_name}</span>
                  <Check className={cn("ml-auto h-4 w-4 shrink-0", isSelected ? "opacity-100" : "opacity-0")} />
                </button>
              )
            })
          ) : (
            <div className="px-3 py-2 text-muted-foreground">没有匹配的颜色代码</div>
          )}
        </div>
      ) : null}
    </div>
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
  const [colorBarcodeOptions, setColorBarcodeOptions] = useState<ProductColorBarcodeItem[]>([])
  const [isLoadingColorBarcodes, setIsLoadingColorBarcodes] = useState(false)

  const title = mode === "create" ? "新增商品" : "编辑商品"
  const lookupDisabled = useMemo(() => {
    return !values.brand || (!values.original_sku.trim() && !values.sku.trim()) || lookupStatus.status === "loading"
  }, [lookupStatus.status, values.brand, values.original_sku, values.sku])

  useEffect(() => {
    setValues(initialValues)
    setLookupStatus({ status: "idle", message: null })
    setSubmitError(null)
    setBrandError(null)
  }, [initialValues, open])

  useEffect(() => {
    if (!open || !values.brand) {
      setColorBarcodeOptions([])
      return
    }

    let cancelled = false
    setIsLoadingColorBarcodes(true)
    listProductColorBarcodes(values.brand as Exclude<BrandKey, "all">)
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

  const handleFieldChange = (field: keyof ProductFormValues, nextValue: string) => {
    setValues((current) => ({ ...current, [field]: nextValue }))

    if (field === "brand") {
      setBrandError(null)
    }

    if (field === "original_sku" || field === "sku") {
      setLookupStatus({ status: "idle", message: null })
    }
  }

  const handleColorCodeChange = (nextValue: string) => {
    const selected = colorBarcodeOptions.find((option) => option.color_code === nextValue)
    setValues((current) => ({
      ...current,
      color_code: nextValue,
      color: selected?.color_name ?? current.color,
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
                            ) : field === "color_code" ? (
                              <ColorCodeSearchSelect
                                id={`product-form-${field}`}
                                value={values.color_code}
                                options={colorBarcodeOptions}
                                isLoading={isLoadingColorBarcodes}
                                disabled={!values.brand || isLoadingColorBarcodes}
                                onChange={handleColorCodeChange}
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
