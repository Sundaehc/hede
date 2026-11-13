import JsBarcode from "jsbarcode"

import type { InventoryPrintLabel, PurchasePrintTemplateConfig, PurchasePrintTemplateElement } from "@/lib/api"

export const LOCAL_LABEL_WIDTH_PX = 640
export const LOCAL_LABEL_HEIGHT_PX = 480

const MIN_MODULE_WIDTH_PX = 2
const QUIET_ZONE_MODULES = 10
export const PURCHASE_EAN_FONT_FAMILY = "monospace"
export type PurchaseBarcodeFormat = "CODE128" | "EAN13"

export function getPurchaseBarcodeData(element: PurchasePrintTemplateElement, data: InventoryPrintLabel) {
  const international = element.field === "international_code"
  return {
    value: international ? String(data.international_code ?? "").trim() : data.barcode,
    format: international ? "EAN13" as const : "CODE128" as const,
  }
}

type BarcodeTarget = { encodings?: Array<{ data: string }> }

// JsBarcode supports its object renderer, but @types/jsbarcode only lists DOM targets.
const encodeBarcode = JsBarcode as unknown as (
  target: BarcodeTarget,
  value: string,
  options: NonNullable<Parameters<typeof JsBarcode>[2]>,
) => void

export function getLocalLabelElementBounds(
  config: PurchasePrintTemplateConfig,
  element: PurchasePrintTemplateElement,
) {
  return {
    x: Math.round(element.x / config.paper_width_mm * LOCAL_LABEL_WIDTH_PX),
    y: Math.round(element.y / config.paper_height_mm * LOCAL_LABEL_HEIGHT_PX),
    width: Math.max(1, Math.round(element.width / config.paper_width_mm * LOCAL_LABEL_WIDTH_PX)),
    height: Math.max(1, Math.round(element.height / config.paper_height_mm * LOCAL_LABEL_HEIGHT_PX)),
  }
}

export function createPurchaseBarcodeLayout(
  value: string,
  width: number,
  height: number,
  border = false,
  format: PurchaseBarcodeFormat = "CODE128",
) {
  const isEan = format === "EAN13"
  if (isEan && !value) {
    throw new Error("商品档案未填写国际码，请维护 13 位国际码后再打印。")
  }
  if (isEan && !/^[0-9]{13}$/.test(value)) {
    throw new Error(`国际码“${value}”必须是 13 位数字，请核对商品档案。`)
  }
  const encodingError = isEan
    ? `国际码“${value}”的 EAN-13 校验码不正确，请核对商品档案。`
    : `条码“${value}”无法生成 Code128，请检查商品编码。`
  const target: BarcodeTarget = {}
  try {
    encodeBarcode(target, value, { format, displayValue: false })
  } catch {
    throw new Error(encodingError)
  }
  const modules = target.encodings?.map((encoding) => encoding.data).join("")
  if (!modules || !/^[01]+$/.test(modules)) {
    throw new Error(encodingError)
  }

  const inset = border ? 1 : 0
  const quietZoneModules = isEan ? 11 : QUIET_ZONE_MODULES
  const moduleWidth = Math.floor((width - inset * 2) / (modules.length + quietZoneModules * 2))
  const fontSize = isEan ? moduleWidth * 9 : 0
  const textHeight = isEan ? Math.ceil(fontSize * 1.2) : 0
  const barHeight = height - inset * 2 - textHeight
  if (moduleWidth < MIN_MODULE_WIDTH_PX || barHeight <= 0 || (isEan && barHeight < moduleWidth * 40)) {
    throw new Error(`条码“${value}”的打印区域不足，请增大模板中的条码${isEan ? "宽度或高度" : "宽度或检查编码长度"}。`)
  }

  const offset = inset + Math.floor((width - inset * 2 - modules.length * moduleWidth) / 2)
  const bars: Array<{ x: number; width: number; height: number }> = []
  for (const match of modules.matchAll(/1+/g)) {
    const guard = isEan && (match.index < 3 || (match.index >= 45 && match.index < 50) || match.index >= 92)
    bars.push({ x: offset + match.index * moduleWidth, width: match[0].length * moduleWidth, height: barHeight + (guard ? moduleWidth * 5 : 0) })
  }
  const text = isEan ? Array.from(value, (digit, index) => ({
    value: digit,
    x: offset + (index === 0 ? -7 : index <= 6 ? 3 + (index - 0.5) * 7 : 50 + (index - 6.5) * 7) * moduleWidth,
    y: height - inset - 1,
    fontSize,
  })) : []

  return {
    width,
    height,
    moduleWidth,
    quietZone: quietZoneModules * moduleWidth,
    y: inset,
    barHeight,
    bars,
    text,
  }
}
