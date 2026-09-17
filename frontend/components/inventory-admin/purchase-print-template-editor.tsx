"use client"

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import JsBarcode from "jsbarcode"
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Copy,
  GripVertical,
  Plus,
  RotateCcw,
  Star,
  Trash2,
  Underline,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/confirm-dialog"
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
import type {
  InventoryPrintLabel,
  PurchasePrintTemplate,
  PurchasePrintTemplateConfig,
  PurchasePrintTemplateElement,
  PurchasePrintTemplateField,
} from "@/lib/api"

const DEFAULT_PAPER_WIDTH = 80
const DEFAULT_PAPER_HEIGHT = 60
const MIN_PAPER_DIMENSION = 20
const MAX_PAPER_DIMENSION = 300
const EDITOR_FONT_SCALE_BASE = 0.44097
const MIN_AUTO_FIT_FONT_SIZE = 5

export const PURCHASE_PRINT_FIELD_OPTIONS: Array<{
  value: PurchasePrintTemplateField
  label: string
}> = [
  { value: "product_code", label: "货号" },
  { value: "size_name", label: "尺码" },
  { value: "brand_name", label: "品牌" },
  { value: "product_level", label: "等级" },
  { value: "color_name", label: "颜色" },
  { value: "upper_material", label: "帮面材质" },
  { value: "product_name", label: "品名" },
  { value: "execution_standard", label: "执行标准" },
  { value: "origin", label: "产地" },
  { value: "barcode", label: "条形码" },
]

const FIELD_LABELS = Object.fromEntries(
  PURCHASE_PRINT_FIELD_OPTIONS.map((option) => [option.value, option.label]),
) as Record<PurchasePrintTemplateField, string>

export const DEFAULT_PURCHASE_PRINT_TEMPLATE: PurchasePrintTemplateConfig = {
  version: 6,
  paper_width_mm: DEFAULT_PAPER_WIDTH,
  paper_height_mm: DEFAULT_PAPER_HEIGHT,
  show_outer_border: true,
  elements: [
    { id: "product-code", kind: "text", field: "product_code", label: "货号", text: "", x: 2, y: 1.1, width: 76, height: 6, font_size: 9.8, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "size", kind: "text", field: "size_name", label: "尺码", text: "", x: 2, y: 7.5, width: 37.3, height: 5.6, font_size: 12, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "level", kind: "text", field: "product_level", label: "等级", text: "", x: 41.3, y: 7.5, width: 36.7, height: 5.6, font_size: 9.2, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "brand", kind: "text", field: "brand_name", label: "品牌", text: "", x: 2, y: 13.9, width: 76, height: 5.3, font_size: 9.5, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "color", kind: "text", field: "color_name", label: "颜色", text: "", x: 2, y: 19.5, width: 76, height: 4.5, font_size: 8.5, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "upper-material", kind: "text", field: "upper_material", label: "帮面材质", text: "", x: 2, y: 24.4, width: 76, height: 4.5, font_size: 8.5, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "product-name", kind: "text", field: "product_name", label: "品名", text: "", x: 2, y: 29.3, width: 76, height: 4.5, font_size: 8.5, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "standard", kind: "text", field: "execution_standard", label: "执行标准", text: "", x: 2, y: 34.1, width: 76, height: 4.5, font_size: 8.5, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "origin", kind: "text", field: "origin", label: "产地", text: "", x: 2, y: 39, width: 76, height: 4.5, font_size: 8.5, bold: true, underline: false, align: "left", show_label: true, border: false, wrap: false },
    { id: "barcode", kind: "barcode", field: "barcode", label: "条形码", text: "", x: 4, y: 44.3, width: 72, height: 10.1, font_size: 8.5, bold: true, underline: false, align: "center", show_label: false, border: false, wrap: false },
    { id: "barcode-value", kind: "text", field: "barcode", label: "条码文字", text: "", x: 4, y: 54.4, width: 47.3, height: 4.1, font_size: 8.5, bold: true, underline: false, align: "left", show_label: false, border: false, wrap: false },
    { id: "barcode-note", kind: "text", field: null, label: "", text: "（内部使用条码）", x: 51.3, y: 54.4, width: 24.7, height: 4.1, font_size: 6.2, bold: false, underline: false, align: "right", show_label: false, border: false, wrap: false },
  ],
}

const PREVIEW_LABEL: InventoryPrintLabel = {
  detail_id: 0,
  product_code: "RH663189DP5",
  size_name: "230",
  size_barcode: "230",
  barcode: "RH663189DP5P5230",
  copies: 1,
  brand: "cbanner_womens",
  brand_name: "C°BANNER",
  product_level: "合格品",
  color_name: "咖色（格利特）",
  upper_material: "牛皮革+合成革",
  product_name: "女休闲鞋",
  execution_standard: "Q/WZHD 002-2022",
  origin: "中国",
}

function cloneTemplate(config: PurchasePrintTemplateConfig): PurchasePrintTemplateConfig {
  return {
    ...config,
    elements: config.elements.map((element) => ({ ...element })),
  }
}

function roundTemplateNumber(value: number) {
  return Math.round(value * 10) / 10
}

function formatPaperDimension(value: number) {
  return (value / 10).toFixed(2)
}

export function resolvePurchasePrintElementText(
  element: PurchasePrintTemplateElement,
  data: InventoryPrintLabel,
) {
  const customLevel = element.field === "product_level" ? element.text.trim() : ""
  const value = customLevel || (element.field ? String(data[element.field] ?? "") : element.text)
  if (!element.field || !element.show_label) return value || "-"
  return `${element.label || FIELD_LABELS[element.field]}：${value || "-"}`
}

function Barcode({ value, className = "" }: { value: string; className?: string }) {
  const ref = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!ref.current || !value) return
    JsBarcode(ref.current, value, {
      format: "CODE128",
      displayValue: false,
      width: 1.35,
      height: 42,
      margin: 0,
      background: "transparent",
      lineColor: "#000000",
    })
  }, [value])

  return <svg ref={ref} className={className} aria-label={`条码 ${value}`} />
}

function AutoFitText({
  fitKey,
  children,
  baseFontSize,
  interactive,
  paperWidth,
  wrap,
  className,
  style,
}: {
  fitKey: string
  children: ReactNode
  baseFontSize: number
  interactive: boolean
  paperWidth: number
  wrap: boolean
  className?: string
  style?: React.CSSProperties
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [fontSize, setFontSize] = useState(baseFontSize)

  const toCssFontSize = (value: number) => interactive
    ? `${value * EDITOR_FONT_SCALE_BASE * (80 / paperWidth)}cqw`
    : `${value}pt`

  useLayoutEffect(() => {
    const node = ref.current
    if (!node) return

    let frame = 0
    const isOverflowing = () => {
      const parent = node.parentElement
      const availableWidth = node.clientWidth || parent?.clientWidth || 0
      const availableHeight = parent?.clientHeight || node.clientHeight || 0
      const widthOverflow = availableWidth > 0 && node.scrollWidth > availableWidth + 0.5
      const heightOverflow = availableHeight > 0 && node.scrollHeight > availableHeight + 0.5
      return widthOverflow || heightOverflow
    }

    const measure = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        node.style.fontSize = toCssFontSize(baseFontSize)
        if (!isOverflowing()) {
          setFontSize((current) => current === baseFontSize ? current : baseFontSize)
          return
        }

        node.style.fontSize = toCssFontSize(MIN_AUTO_FIT_FONT_SIZE)
        if (isOverflowing()) {
          setFontSize((current) => current === MIN_AUTO_FIT_FONT_SIZE ? current : MIN_AUTO_FIT_FONT_SIZE)
          return
        }

        let low = MIN_AUTO_FIT_FONT_SIZE
        let high = baseFontSize
        for (let index = 0; index < 8; index += 1) {
          const middle = (low + high) / 2
          node.style.fontSize = toCssFontSize(middle)
          if (isOverflowing()) high = middle
          else low = middle
        }
        const fitted = Math.round(low * 100) / 100
        setFontSize((current) => current === fitted ? current : fitted)
      })
    }

    measure()
    const observer = new ResizeObserver(measure)
    if (node.parentElement) observer.observe(node.parentElement)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [baseFontSize, fitKey, interactive, paperWidth, wrap])

  return (
    <div
      ref={ref}
      className={className}
      style={{
        ...style,
        fontSize: toCssFontSize(fontSize),
        whiteSpace: wrap ? "normal" : "nowrap",
        overflowWrap: wrap ? "anywhere" : "normal",
      }}
    >
      {children}
    </div>
  )
}

export function PurchasePrintTemplateContent({
  config,
  data,
  selectedId,
  interactive = false,
  onSelect,
  onPointerStart,
}: {
  config: PurchasePrintTemplateConfig
  data: InventoryPrintLabel
  selectedId?: string | null
  interactive?: boolean
  onSelect?: (id: string) => void
  onPointerStart?: (event: React.PointerEvent, element: PurchasePrintTemplateElement, mode: "move" | "resize") => void
}) {
  const paperWidth = config.paper_width_mm
  const paperHeight = config.paper_height_mm
  return (
    <>
      {config.elements.map((element) => {
        const style: React.CSSProperties = {
          left: `${(element.x / paperWidth) * 100}%`,
          top: `${(element.y / paperHeight) * 100}%`,
          width: `${(element.width / paperWidth) * 100}%`,
          height: `${(element.height / paperHeight) * 100}%`,
          fontSize: interactive
            ? `${element.font_size * EDITOR_FONT_SCALE_BASE * (80 / paperWidth)}cqw`
            : `${element.font_size}pt`,
          fontWeight: element.bold ? 700 : 400,
          textDecorationLine: element.kind === "text" && element.underline ? "underline" : undefined,
          textAlign: element.align,
          border: element.border ? "1px solid #000" : undefined,
          whiteSpace: element.wrap ? "normal" : "nowrap",
        }
        const isSelected = interactive && selectedId === element.id
        return (
          <div
            key={element.id}
            className={`purchase-print-element ${interactive ? "cursor-move touch-none select-none" : ""} ${isSelected ? "purchase-print-element-selected" : ""}`}
            style={style}
            onClick={(event) => {
              if (!interactive) return
              event.stopPropagation()
              onSelect?.(element.id)
            }}
            onPointerDown={(event) => interactive && onPointerStart?.(event, element, "move")}
          >
            {element.kind === "barcode" ? (
              <Barcode value={data.barcode} className="purchase-print-barcode" />
            ) : (
              <AutoFitText
                fitKey={[
                  element.id,
                  resolvePurchasePrintElementText(element, data),
                  element.bold,
                  element.width,
                  element.height,
                ].join(":")}
                baseFontSize={element.font_size}
                interactive={interactive}
                paperWidth={paperWidth}
                wrap={element.wrap}
                className="purchase-print-text"
                style={{
                  fontWeight: element.bold ? 700 : 400,
                  textDecorationLine: element.underline ? "underline" : undefined,
                }}
              >
                {resolvePurchasePrintElementText(element, data)}
              </AutoFitText>
            )}
            {isSelected && (
              <button
                type="button"
                className="purchase-print-resize-handle"
                aria-label="调整元素大小"
                title="拖动调整大小"
                onPointerDown={(event) => onPointerStart?.(event, element, "resize")}
              />
            )}
          </div>
        )
      })}
    </>
  )
}

type Interaction = {
  id: string
  mode: "move" | "resize"
  startX: number
  startY: number
  initial: PurchasePrintTemplateElement
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function nextElementId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function PurchasePrintTemplateEditor({
  open,
  config,
  templates,
  selectedTemplateKey,
  templateName,
  onOpenChange,
  onTemplateChange,
  onCreateTemplate,
  onDuplicateTemplate,
  onSetDefaultTemplate,
  onDeleteTemplate,
  onSave,
}: {
  open: boolean
  config: PurchasePrintTemplateConfig
  templates: PurchasePrintTemplate[]
  selectedTemplateKey: string
  templateName: string
  onOpenChange: (open: boolean) => void
  onTemplateChange: (templateKey: string) => void
  onCreateTemplate: (templateName: string, config: PurchasePrintTemplateConfig) => Promise<void>
  onDuplicateTemplate: (templateName: string, config: PurchasePrintTemplateConfig) => Promise<void>
  onSetDefaultTemplate: () => Promise<void>
  onDeleteTemplate: () => Promise<void>
  onSave: (config: PurchasePrintTemplateConfig, templateName: string) => Promise<void>
}) {
  const [draft, setDraft] = useState(() => cloneTemplate(config))
  const [selectedId, setSelectedId] = useState<string | null>(config.elements[0]?.id ?? null)
  const [fieldToAdd, setFieldToAdd] = useState<PurchasePrintTemplateField>("product_code")
  const [isSaving, setIsSaving] = useState(false)
  const [templateNameInput, setTemplateNameInput] = useState(templateName)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [paperWidthInput, setPaperWidthInput] = useState(formatPaperDimension(config.paper_width_mm))
  const [paperHeightInput, setPaperHeightInput] = useState(formatPaperDimension(config.paper_height_mm))
  const [previewSize, setPreviewSize] = useState({ width: 0, height: 0 })
  const previewViewportRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const interactionRef = useRef<Interaction | null>(null)

  useEffect(() => {
    if (!open) return
    const next = cloneTemplate(config)
    setDraft(next)
    setSelectedId(next.elements[0]?.id ?? null)
    setPaperWidthInput(formatPaperDimension(next.paper_width_mm))
    setPaperHeightInput(formatPaperDimension(next.paper_height_mm))
    setTemplateNameInput(templateName)
  }, [config, open, templateName])

  useEffect(() => {
    if (!open || !previewViewportRef.current) return
    const viewport = previewViewportRef.current
    const updatePreviewSize = () => {
      const bounds = viewport.getBoundingClientRect()
      const availableWidth = Math.max(0, bounds.width - 2)
      const availableHeight = Math.max(0, bounds.height - 2)
      const scale = Math.min(
        availableWidth / draft.paper_width_mm,
        availableHeight / draft.paper_height_mm,
      )
      if (!Number.isFinite(scale) || scale <= 0) return
      setPreviewSize({
        width: Math.max(1, Math.floor(draft.paper_width_mm * scale)),
        height: Math.max(1, Math.floor(draft.paper_height_mm * scale)),
      })
    }
    updatePreviewSize()
    const observer = new ResizeObserver(updatePreviewSize)
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [draft.paper_height_mm, draft.paper_width_mm, open])

  useEffect(() => {
    if (!open) return
    const handleMove = (event: PointerEvent) => {
      const interaction = interactionRef.current
      const canvas = canvasRef.current
      if (!interaction || !canvas) return
      const bounds = canvas.getBoundingClientRect()
      setDraft((current) => ({
        ...current,
        elements: current.elements.map((element) => {
          if (element.id !== interaction.id) return element
          const deltaX = ((event.clientX - interaction.startX) / bounds.width) * current.paper_width_mm
          const deltaY = ((event.clientY - interaction.startY) / bounds.height) * current.paper_height_mm
          if (interaction.mode === "move") {
            return {
              ...element,
              x: roundTemplateNumber(clamp(interaction.initial.x + deltaX, 0, current.paper_width_mm - element.width)),
              y: roundTemplateNumber(clamp(interaction.initial.y + deltaY, 0, current.paper_height_mm - element.height)),
            }
          }
          return {
            ...element,
            width: roundTemplateNumber(clamp(interaction.initial.width + deltaX, 3, current.paper_width_mm - element.x)),
            height: roundTemplateNumber(clamp(interaction.initial.height + deltaY, 2, current.paper_height_mm - element.y)),
          }
        }),
      }))
    }
    const handleUp = () => { interactionRef.current = null }
    window.addEventListener("pointermove", handleMove)
    window.addEventListener("pointerup", handleUp)
    return () => {
      window.removeEventListener("pointermove", handleMove)
      window.removeEventListener("pointerup", handleUp)
    }
  }, [open])

  const selected = useMemo(
    () => draft.elements.find((element) => element.id === selectedId) ?? null,
    [draft.elements, selectedId],
  )

  const updateSelected = (values: Partial<PurchasePrintTemplateElement>) => {
    if (!selectedId) return
    setDraft((current) => ({
      ...current,
      elements: current.elements.map((element) => element.id === selectedId ? { ...element, ...values } : element),
    }))
  }

  const updatePaperDimension = (key: "paper_width_mm" | "paper_height_mm", value: number) => {
    if (!Number.isFinite(value)) return
    const nextValue = clamp(value, MIN_PAPER_DIMENSION, MAX_PAPER_DIMENSION)
    setDraft((current) => {
      const previousValue = current[key]
      if (previousValue === nextValue) return current
      const ratio = nextValue / previousValue
      const scaleX = key === "paper_width_mm" ? ratio : 1
      const scaleY = key === "paper_height_mm" ? ratio : 1
      return {
        ...current,
        [key]: nextValue,
        elements: current.elements.map((element) => ({
          ...element,
          x: roundTemplateNumber(element.x * scaleX),
          y: roundTemplateNumber(element.y * scaleY),
          width: roundTemplateNumber(element.width * scaleX),
          height: roundTemplateNumber(element.height * scaleY),
        })),
      }
    })
  }

  const commitPaperDimension = (key: "paper_width_mm" | "paper_height_mm", input: string) => {
    const centimeters = Number(input)
    if (!Number.isFinite(centimeters)) {
      const currentValue = draft[key]
      if (key === "paper_width_mm") setPaperWidthInput(formatPaperDimension(currentValue))
      else setPaperHeightInput(formatPaperDimension(currentValue))
      return
    }
    updatePaperDimension(key, centimeters * 10)
    const nextInput = formatPaperDimension(clamp(centimeters * 10, MIN_PAPER_DIMENSION, MAX_PAPER_DIMENSION))
    if (key === "paper_width_mm") setPaperWidthInput(nextInput)
    else setPaperHeightInput(nextInput)
  }

  const addElement = (field: PurchasePrintTemplateField | null) => {
    const isBarcode = field === "barcode"
    const id = nextElementId(field || "fixed-text")
    const offset = (draft.elements.length % 8) * 1.2
    if (isBarcode) {
      const width = Math.min(54, draft.paper_width_mm - 6)
      const x = clamp(3 + offset, 0, draft.paper_width_mm - width)
      const y = clamp(4 + offset, 0, draft.paper_height_mm - 19)
      const valueWidth = roundTemplateNumber(width * 0.66)
      const noteWidth = roundTemplateNumber(width - valueWidth)
      const elements: PurchasePrintTemplateElement[] = [
        { id, kind: "barcode", field: "barcode", label: "条形码", text: "", x, y, width, height: 13.5, font_size: 8.5, bold: true, underline: false, align: "center", show_label: false, border: false, wrap: false },
        { id: `${id}-value`, kind: "text", field: "barcode", label: "条码文字", text: "", x, y: y + 13.5, width: valueWidth, height: 5.5, font_size: 8.5, bold: true, underline: false, align: "left", show_label: false, border: false, wrap: false },
        { id: `${id}-note`, kind: "text", field: null, label: "", text: "（内部使用条码）", x: x + valueWidth, y: y + 13.5, width: noteWidth, height: 5.5, font_size: 6.2, bold: false, underline: false, align: "right", show_label: false, border: false, wrap: false },
      ]
      setDraft((current) => ({ ...current, elements: [...current.elements, ...elements] }))
      setSelectedId(id)
      return
    }
    const next: PurchasePrintTemplateElement = {
      id,
      kind: "text",
      field,
      label: field ? FIELD_LABELS[field] : "",
      text: field ? "" : "固定文字",
      x: clamp(4 + offset, 0, draft.paper_width_mm - 30),
      y: clamp(4 + offset, 0, draft.paper_height_mm - 5),
      width: Math.min(30, draft.paper_width_mm - 6),
      height: 5,
      font_size: 9,
      bold: false,
      underline: false,
      align: "left",
      show_label: Boolean(field),
      border: false,
      wrap: false,
    }
    setDraft((current) => ({ ...current, elements: [...current.elements, next] }))
    setSelectedId(id)
  }

  const removeSelected = () => {
    if (!selectedId) return
    setDraft((current) => {
      const elements = current.elements.filter((element) => element.id !== selectedId)
      setSelectedId(elements[0]?.id ?? null)
      return { ...current, elements }
    })
  }

  const startInteraction = (
    event: React.PointerEvent,
    element: PurchasePrintTemplateElement,
    mode: "move" | "resize",
  ) => {
    event.preventDefault()
    event.stopPropagation()
    setSelectedId(element.id)
    interactionRef.current = {
      id: element.id,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      initial: { ...element },
    }
  }

  const handleSave = async () => {
    if (draft.elements.length === 0) return
    setIsSaving(true)
    try {
      await onSave(draft, templateNameInput.trim() || "默认模板")
      onOpenChange(false)
    } catch {
      // The parent presents the API error and keeps the editor open.
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(760px,94vh)] max-w-[1180px] flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-border px-5 py-4">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <DialogTitle>鞋盒标签模板</DialogTitle>
            <div className="flex min-w-0 items-center gap-2">
              <Select
                className="w-[190px]"
                value={selectedTemplateKey}
                onChange={(event) => onTemplateChange(event.target.value)}
                aria-label="选择标签模板"
              >
                {templates.map((template) => (
                  <option key={template.template_key} value={template.template_key}>
                    {template.template_name}{template.is_default ? "（默认）" : ""}
                  </option>
                ))}
              </Select>
              <Button type="button" variant="outline" size="icon" title="新建模板" aria-label="新建模板" onClick={() => void onCreateTemplate("新模板", cloneTemplate(DEFAULT_PURCHASE_PRINT_TEMPLATE))}>
                <Plus className="size-4" />
              </Button>
              <Button type="button" variant="outline" size="icon" title="复制当前模板" aria-label="复制当前模板" onClick={() => void onDuplicateTemplate(`${templateNameInput.trim() || "模板"}-副本`, cloneTemplate(draft))}>
                <Copy className="size-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>
        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(300px,1fr)_minmax(0,0.85fr)] overflow-hidden lg:grid-cols-[minmax(0,1fr)_330px] lg:grid-rows-1">
          <div className="flex min-h-0 flex-col bg-muted/30 p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{draft.paper_width_mm} × {draft.paper_height_mm} mm</p>
                <p className="text-xs text-muted-foreground">拖动元素调整位置，拖动右下角调整大小</p>
              </div>
              <Button type="button" variant="outline" size="sm" onClick={() => {
                const next = cloneTemplate(DEFAULT_PURCHASE_PRINT_TEMPLATE)
                setDraft(next)
                setSelectedId(next.elements[0]?.id ?? null)
                setPaperWidthInput(formatPaperDimension(next.paper_width_mm))
                setPaperHeightInput(formatPaperDimension(next.paper_height_mm))
              }}>
                <RotateCcw className="size-3.5" />载入默认
              </Button>
            </div>
            <div ref={previewViewportRef} className="flex min-h-0 flex-1 items-center justify-center overflow-auto rounded-lg border border-border bg-zinc-200/70 p-7 shadow-inner">
              <div
                ref={canvasRef}
                className="purchase-template-canvas relative shrink-0 overflow-hidden bg-white text-black shadow-[0_12px_35px_rgba(0,0,0,0.18)]"
                style={{
                  width: previewSize.width || undefined,
                  height: previewSize.height || undefined,
                  aspectRatio: `${draft.paper_width_mm} / ${draft.paper_height_mm}`,
                }}
                data-outer-border={draft.show_outer_border}
                onClick={() => setSelectedId(null)}
              >
                <PurchasePrintTemplateContent
                  config={draft}
                  data={PREVIEW_LABEL}
                  selectedId={selectedId}
                  interactive
                  onSelect={setSelectedId}
                  onPointerStart={startInteraction}
                />
              </div>
            </div>
          </div>

          <aside className="min-h-0 overflow-y-auto border-t border-border bg-background p-4 lg:border-t-0 lg:border-l">
            <div className="space-y-4">
              <div className="space-y-2 border-b border-border pb-4">
                <Label htmlFor="purchase-print-template-name">模板名称</Label>
                <Input
                  id="purchase-print-template-name"
                  value={templateNameInput}
                  maxLength={80}
                  onChange={(event) => setTemplateNameInput(event.target.value)}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="cursor-pointer"
                    disabled={templates.find((item) => item.template_key === selectedTemplateKey)?.is_default}
                    onClick={() => void onSetDefaultTemplate()}
                  >
                    <Star className="size-3.5" />设为默认
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="cursor-pointer text-destructive"
                    disabled={templates.length <= 1}
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    <Trash2 className="size-3.5" />删除模板
                  </Button>
                </div>
              </div>
              <div className="space-y-2 border-b border-border pb-4">
                <Label>模板配置</Label>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="print-paper-width">模板宽度（厘米）</Label>
                    <Input
                      id="print-paper-width"
                      type="number"
                      min={MIN_PAPER_DIMENSION / 10}
                      max={MAX_PAPER_DIMENSION / 10}
                      step="0.01"
                      value={paperWidthInput}
                      onChange={(event) => setPaperWidthInput(event.target.value)}
                      onBlur={() => commitPaperDimension("paper_width_mm", paperWidthInput)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.currentTarget.blur()
                      }}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="print-paper-height">模板高度（厘米）</Label>
                    <Input
                      id="print-paper-height"
                      type="number"
                      min={MIN_PAPER_DIMENSION / 10}
                      max={MAX_PAPER_DIMENSION / 10}
                      step="0.01"
                      value={paperHeightInput}
                      onChange={(event) => setPaperHeightInput(event.target.value)}
                      onBlur={() => commitPaperDimension("paper_height_mm", paperHeightInput)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.currentTarget.blur()
                      }}
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">尺寸范围 2–30 厘米，调整后元素会按比例缩放</p>
              </div>

              <div className="space-y-2 border-b border-border pb-4">
                <Label>添加内容</Label>
                <div className="flex gap-2">
                  <Select value={fieldToAdd} onChange={(event) => setFieldToAdd(event.target.value as PurchasePrintTemplateField)}>
                    {PURCHASE_PRINT_FIELD_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </Select>
                  <Button type="button" variant="outline" size="icon" title="添加字段" aria-label="添加字段" onClick={() => addElement(fieldToAdd)}>
                    <Plus className="size-4" />
                  </Button>
                </div>
                <Button type="button" variant="outline" size="sm" className="w-full" onClick={() => addElement(null)}>
                  <Plus className="size-3.5" />添加固定文字
                </Button>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input type="checkbox" checked={draft.show_outer_border} onChange={(event) => setDraft((current) => ({ ...current, show_outer_border: event.target.checked }))} />
                  显示标签外边框
                </label>
              </div>

              {!selected ? (
                <div className="flex min-h-48 flex-col items-center justify-center text-center text-muted-foreground">
                  <GripVertical className="mb-2 size-5" />
                  <p className="text-sm">选择画布中的内容进行编辑</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium">{selected.field ? FIELD_LABELS[selected.field] : "固定文字"}</p>
                      <p className="text-xs text-muted-foreground">位置与内容</p>
                    </div>
                    <Button type="button" variant="ghost" size="icon" className="text-destructive" title="删除元素" aria-label="删除元素" onClick={removeSelected}>
                      <Trash2 className="size-4" />
                    </Button>
                  </div>

                  {selected.kind === "text" && selected.field && (
                    <div className="space-y-1.5">
                      <Label htmlFor="print-element-label">字段标题</Label>
                      <Input id="print-element-label" value={selected.label} onChange={(event) => updateSelected({ label: event.target.value })} />
                    </div>
                  )}
                  {selected.kind === "text" && selected.field === "product_level" && (
                    <div className="space-y-1.5">
                      <Label htmlFor="print-element-level">等级内容</Label>
                      <Input
                        id="print-element-level"
                        value={selected.text}
                        placeholder="合格品"
                        maxLength={200}
                        onChange={(event) => updateSelected({ text: event.target.value })}
                      />
                    </div>
                  )}
                  {selected.kind === "text" && !selected.field && (
                    <div className="space-y-1.5">
                      <Label htmlFor="print-element-text">固定文字</Label>
                      <Input id="print-element-text" value={selected.text} onChange={(event) => updateSelected({ text: event.target.value })} />
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-2">
                    {([
                      ["x", "横坐标", 0, draft.paper_width_mm - selected.width],
                      ["y", "纵坐标", 0, draft.paper_height_mm - selected.height],
                      ["width", "宽度", 3, draft.paper_width_mm - selected.x],
                      ["height", "高度", 2, draft.paper_height_mm - selected.y],
                    ] as const).map(([key, label, minimum, maximum]) => (
                      <div className="space-y-1.5" key={key}>
                        <Label htmlFor={`print-element-${key}`}>{label} (mm)</Label>
                        <Input
                          id={`print-element-${key}`}
                          type="number"
                          step="0.5"
                          min={minimum}
                          max={maximum}
                          value={selected[key]}
                          onChange={(event) => updateSelected({ [key]: clamp(Number(event.target.value), minimum, maximum) })}
                        />
                      </div>
                    ))}
                  </div>

                  {selected.kind === "text" && (
                    <>
                      <div className="space-y-1.5">
                        <Label htmlFor="print-element-font-size">字号 (pt)</Label>
                        <Input id="print-element-font-size" type="number" min="5" max="30" step="0.5" value={selected.font_size} onChange={(event) => updateSelected({ font_size: clamp(Number(event.target.value), 5, 30) })} />
                      </div>
                      <div className="flex items-center gap-2">
                        <Button type="button" variant={selected.bold ? "secondary" : "outline"} size="icon" title="粗体" aria-label="粗体" onClick={() => updateSelected({ bold: !selected.bold })}>
                          <Bold className="size-4" />
                        </Button>
                        <Button type="button" variant={selected.underline ? "secondary" : "outline"} size="icon" title="下划线" aria-label="下划线" onClick={() => updateSelected({ underline: !selected.underline })}>
                          <Underline className="size-4" />
                        </Button>
                        {([[
                          "left", AlignLeft, "左对齐",
                        ], [
                          "center", AlignCenter, "居中",
                        ], [
                          "right", AlignRight, "右对齐",
                        ]] as const).map(([align, Icon, title]) => (
                          <Button key={align} type="button" variant={selected.align === align ? "secondary" : "outline"} size="icon" title={title} aria-label={title} onClick={() => updateSelected({ align })}>
                            <Icon className="size-4" />
                          </Button>
                        ))}
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        {selected.field && (
                          <label className="flex cursor-pointer items-center gap-2">
                            <input type="checkbox" checked={selected.show_label} onChange={(event) => updateSelected({ show_label: event.target.checked })} />显示标题
                          </label>
                        )}
                        <label className="flex cursor-pointer items-center gap-2">
                          <input type="checkbox" checked={selected.border} onChange={(event) => updateSelected({ border: event.target.checked })} />显示边框
                        </label>
                        <label className="flex cursor-pointer items-center gap-2">
                          <input type="checkbox" checked={selected.wrap} onChange={(event) => updateSelected({ wrap: event.target.checked })} />允许换行
                        </label>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </aside>
        </div>
      <DialogFooter className="border-t border-border px-5 py-3">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button type="button" disabled={isSaving || draft.elements.length === 0} onClick={() => void handleSave()}>
            {isSaving ? "保存中..." : "保存模板"}
          </Button>
      </DialogFooter>
      </DialogContent>
      <ConfirmDialog
        open={deleteConfirmOpen}
        title="删除标签模板"
        description={`确定删除“${templateNameInput || "当前模板"}”吗？删除后无法恢复。`}
        confirmLabel="删除"
        variant="destructive"
        onConfirm={() => {
          setDeleteConfirmOpen(false)
          void onDeleteTemplate()
        }}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </Dialog>
  )
}
