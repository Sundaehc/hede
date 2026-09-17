import JsBarcode from "jsbarcode"

import { resolvePurchasePrintElementText } from "@/components/inventory-admin/purchase-print-template-editor"
import type {
  InventoryPrintLabel,
  PurchasePrintTemplateConfig,
  PurchasePrintTemplateElement,
} from "@/lib/api"

const LABEL_WIDTH_PX = 640
const LABEL_HEIGHT_PX = 480
const LABEL_WIDTH_MM = 80
const LABEL_HEIGHT_MM = 60
const PRINTER_DPI = 203
const MIN_FONT_SIZE_PT = 5
const PRINT_AGENT_URL = (
  process.env.NEXT_PUBLIC_TSC_PRINT_AGENT_URL || "http://127.0.0.1:18120"
).replace(/\/+$/, "")

const FONT_FAMILY = '"Microsoft YaHei", "SimSun", sans-serif'

export const LOCAL_PRINT_AGENT_UNAVAILABLE_MESSAGE =
  "本机打印服务未启动，请在连接 TSCTTP-244 Pro 的电脑上启动 Hede 打印服务。"

type TextLayout = {
  fontSizePx: number
  lines: string[]
  lineHeightPx: number
}

export type LocalLabelBitmap = {
  width: number
  height: number
  data_base64: string
}

export type LocalLabelPrintResult = {
  ok: boolean
  printed: number
  printer: string
}

export class LocalLabelPrintError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LocalLabelPrintError"
  }
}

function pointToPixel(value: number) {
  return value * PRINTER_DPI / 72
}

function setCanvasFont(
  context: CanvasRenderingContext2D,
  element: PurchasePrintTemplateElement,
  fontSizePx: number,
) {
  context.font = `${element.bold ? 700 : 400} ${fontSizePx}px ${FONT_FAMILY}`
}

function splitTextIntoLines(
  context: CanvasRenderingContext2D,
  text: string,
  maximumWidth: number,
  wrap: boolean,
) {
  if (!wrap) return [text.replace(/\s*\n\s*/g, " ")]

  const lines: string[] = []
  for (const paragraph of text.split(/\r?\n/)) {
    if (!paragraph) {
      lines.push("")
      continue
    }
    let line = ""
    for (const character of Array.from(paragraph)) {
      const candidate = `${line}${character}`
      if (line && context.measureText(candidate).width > maximumWidth) {
        lines.push(line)
        line = character
      } else {
        line = candidate
      }
    }
    lines.push(line)
  }
  return lines.length ? lines : [""]
}

function layoutText(
  context: CanvasRenderingContext2D,
  element: PurchasePrintTemplateElement,
  text: string,
  width: number,
  height: number,
): TextLayout {
  const maximumFontSizePx = pointToPixel(element.font_size)
  const minimumFontSizePx = Math.min(maximumFontSizePx, pointToPixel(MIN_FONT_SIZE_PT))
  let low = minimumFontSizePx
  let high = maximumFontSizePx
  let best: TextLayout | null = null

  for (let index = 0; index < 12; index += 1) {
    const fontSizePx = index === 0 ? high : (low + high) / 2
    setCanvasFont(context, element, fontSizePx)
    const lines = splitTextIntoLines(context, text, width, element.wrap)
    const lineHeightPx = fontSizePx * 1.12
    const fitsWidth = lines.every((line) => context.measureText(line).width <= width + 0.25)
    const fitsHeight = lines.length * lineHeightPx <= height + 0.25
    if (fitsWidth && fitsHeight) {
      best = { fontSizePx, lines, lineHeightPx }
      low = fontSizePx
    } else {
      high = fontSizePx
    }
  }

  if (best) return best
  setCanvasFont(context, element, minimumFontSizePx)
  return {
    fontSizePx: minimumFontSizePx,
    lines: splitTextIntoLines(context, text, width, element.wrap),
    lineHeightPx: minimumFontSizePx * 1.12,
  }
}

function drawUnderline(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  align: PurchasePrintTemplateElement["align"],
) {
  const width = context.measureText(text).width
  const startX = align === "center" ? x - width / 2 : align === "right" ? x - width : x
  context.beginPath()
  context.moveTo(startX, y)
  context.lineTo(startX + width, y)
  context.lineWidth = 1
  context.strokeStyle = "#000"
  context.stroke()
}

function drawTextElement(
  context: CanvasRenderingContext2D,
  element: PurchasePrintTemplateElement,
  data: InventoryPrintLabel,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  const text = resolvePurchasePrintElementText(element, data)
  const layout = layoutText(context, element, text, width, height)
  setCanvasFont(context, element, layout.fontSizePx)
  context.fillStyle = "#000"
  context.textAlign = element.align
  context.textBaseline = "middle"

  const textX = element.align === "center" ? x + width / 2 : element.align === "right" ? x + width : x
  const contentHeight = layout.lines.length * layout.lineHeightPx
  const firstLineCenterY = y + (height - contentHeight) / 2 + layout.lineHeightPx / 2
  layout.lines.forEach((line, lineIndex) => {
    const centerY = firstLineCenterY + lineIndex * layout.lineHeightPx
    context.fillText(line, textX, centerY)
    if (element.underline && line) {
      drawUnderline(
        context,
        line,
        textX,
        centerY + layout.fontSizePx * 0.43,
        element.align,
      )
    }
  })
}

function drawBarcodeElement(
  context: CanvasRenderingContext2D,
  value: string,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  if (!value) return
  const barcodeCanvas = document.createElement("canvas")
  JsBarcode(barcodeCanvas, value, {
    format: "CODE128",
    displayValue: false,
    width: 2,
    height: Math.max(1, Math.round(height)),
    margin: 0,
    background: "#ffffff",
    lineColor: "#000000",
  })
  context.save()
  context.imageSmoothingEnabled = false
  context.drawImage(barcodeCanvas, x, y, width, height)
  context.restore()
}

function drawTemplateElement(
  context: CanvasRenderingContext2D,
  config: PurchasePrintTemplateConfig,
  element: PurchasePrintTemplateElement,
  data: InventoryPrintLabel,
) {
  const x = Math.round(element.x / config.paper_width_mm * LABEL_WIDTH_PX)
  const y = Math.round(element.y / config.paper_height_mm * LABEL_HEIGHT_PX)
  const width = Math.max(1, Math.round(element.width / config.paper_width_mm * LABEL_WIDTH_PX))
  const height = Math.max(1, Math.round(element.height / config.paper_height_mm * LABEL_HEIGHT_PX))

  context.save()
  context.beginPath()
  context.rect(x, y, width, height)
  context.clip()
  if (element.kind === "barcode") {
    drawBarcodeElement(context, data.barcode, x, y, width, height)
  } else {
    drawTextElement(context, element, data, x, y, width, height)
  }
  context.restore()

  if (element.border) {
    context.save()
    context.strokeStyle = "#000"
    context.lineWidth = 1
    context.strokeRect(x + 0.5, y + 0.5, Math.max(0, width - 1), Math.max(0, height - 1))
    context.restore()
  }
}

export function packMonochromePixels(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
) {
  if (width <= 0 || height <= 0 || width % 8 !== 0) {
    throw new Error("标签位图宽度必须是 8 的正整数倍")
  }
  if (pixels.length !== width * height * 4) {
    throw new Error("标签像素数据长度不正确")
  }

  const packed = new Uint8Array(width / 8 * height)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const pixelOffset = (y * width + x) * 4
      const alpha = pixels[pixelOffset + 3] / 255
      const luminance = (
        pixels[pixelOffset] * 0.299
        + pixels[pixelOffset + 1] * 0.587
        + pixels[pixelOffset + 2] * 0.114
      ) * alpha + 255 * (1 - alpha)
      if (luminance < 200) {
        const byteOffset = y * (width / 8) + Math.floor(x / 8)
        packed[byteOffset] |= 0x80 >> (x % 8)
      }
    }
  }
  return packed
}

function bytesToBase64(bytes: Uint8Array) {
  let binary = ""
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return window.btoa(binary)
}

export async function renderLocalLabelBitmap(
  data: InventoryPrintLabel,
  config: PurchasePrintTemplateConfig,
): Promise<LocalLabelBitmap> {
  await document.fonts?.ready
  const canvas = document.createElement("canvas")
  canvas.width = LABEL_WIDTH_PX
  canvas.height = LABEL_HEIGHT_PX
  const context = canvas.getContext("2d", { willReadFrequently: true })
  if (!context) throw new LocalLabelPrintError("当前浏览器无法生成标签位图")

  context.fillStyle = "#fff"
  context.fillRect(0, 0, canvas.width, canvas.height)
  config.elements.forEach((element) => drawTemplateElement(context, config, element, data))
  if (config.show_outer_border) {
    const border = config.outer_border
    const x = border.x / config.paper_width_mm * LABEL_WIDTH_PX
    const y = border.y / config.paper_height_mm * LABEL_HEIGHT_PX
    const width = border.width / config.paper_width_mm * LABEL_WIDTH_PX
    const height = border.height / config.paper_height_mm * LABEL_HEIGHT_PX
    const lineWidth = Math.max(1, border.line_width / config.paper_width_mm * LABEL_WIDTH_PX)
    const inset = lineWidth / 2
    context.strokeStyle = "#000"
    context.lineWidth = lineWidth
    context.strokeRect(
      x + inset,
      y + inset,
      Math.max(0, width - lineWidth),
      Math.max(0, height - lineWidth),
    )
  }

  const image = context.getImageData(0, 0, LABEL_WIDTH_PX, LABEL_HEIGHT_PX)
  return {
    width: LABEL_WIDTH_PX,
    height: LABEL_HEIGHT_PX,
    data_base64: bytesToBase64(packMonochromePixels(image.data, LABEL_WIDTH_PX, LABEL_HEIGHT_PX)),
  }
}

async function readPrintAgentError(response: Response) {
  try {
    const result = await response.json() as { error?: unknown }
    if (typeof result.error === "string" && result.error.trim()) return result.error
  } catch {
    // The local agent may have returned a plain-text proxy or system error.
  }
  return `本机打印服务返回错误（${response.status}）`
}

export async function printLabelsWithLocalAgent(
  labels: InventoryPrintLabel[],
  config: PurchasePrintTemplateConfig,
): Promise<LocalLabelPrintResult> {
  const bitmaps: LocalLabelBitmap[] = []
  for (let index = 0; index < labels.length; index += 1) {
    bitmaps.push(await renderLocalLabelBitmap(labels[index], config))
    if ((index + 1) % 10 === 0) {
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()))
    }
  }

  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  try {
    const response = await fetch(`${PRINT_AGENT_URL}/print`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paper_width_mm: LABEL_WIDTH_MM,
        paper_height_mm: LABEL_HEIGHT_MM,
        labels: bitmaps,
      }),
      signal: controller.signal,
    })
    if (!response.ok) throw new LocalLabelPrintError(await readPrintAgentError(response))
    return await response.json() as LocalLabelPrintResult
  } catch (error) {
    if (error instanceof LocalLabelPrintError) throw error
    throw new LocalLabelPrintError(LOCAL_PRINT_AGENT_UNAVAILABLE_MESSAGE)
  } finally {
    window.clearTimeout(timeout)
  }
}
