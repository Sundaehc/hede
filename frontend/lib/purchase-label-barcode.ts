import JsBarcode from "jsbarcode"

import type { PurchasePrintTemplateConfig, PurchasePrintTemplateElement } from "@/lib/api"

export const LOCAL_LABEL_WIDTH_PX = 640
export const LOCAL_LABEL_HEIGHT_PX = 480

const MIN_MODULE_WIDTH_PX = 2
const QUIET_ZONE_MODULES = 10

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
) {
  const target: BarcodeTarget = {}
  try {
    encodeBarcode(target, value, { format: "CODE128", displayValue: false })
  } catch {
    throw new Error(`条码“${value}”无法生成 Code128，请检查商品编码。`)
  }
  const modules = target.encodings?.map((encoding) => encoding.data).join("")
  if (!modules || !/^[01]+$/.test(modules)) {
    throw new Error(`条码“${value}”无法生成 Code128，请检查商品编码。`)
  }

  const inset = border ? 1 : 0
  const moduleWidth = Math.floor((width - inset * 2) / (modules.length + QUIET_ZONE_MODULES * 2))
  if (moduleWidth < MIN_MODULE_WIDTH_PX || height <= inset * 2) {
    throw new Error(`条码“${value}”的打印区域不足，请增大模板中的条码宽度或检查编码长度。`)
  }

  const offset = inset + Math.floor((width - inset * 2 - modules.length * moduleWidth) / 2)
  const bars: Array<{ x: number; width: number }> = []
  for (const match of modules.matchAll(/1+/g)) {
    bars.push({ x: offset + match.index * moduleWidth, width: match[0].length * moduleWidth })
  }

  return {
    width,
    height,
    moduleWidth,
    quietZone: QUIET_ZONE_MODULES * moduleWidth,
    y: inset,
    barHeight: height - inset * 2,
    bars,
  }
}
