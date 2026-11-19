"use client"

import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react"

export function PurchaseDetailColumnResizeHandle({
  label, width, defaultWidth, min, max, onPreview, onCommit,
}: {
  label: string
  width: number
  defaultWidth: number
  min: number
  max: number
  onPreview: (width: number | null) => void
  onCommit: (width: number) => void
}) {
  const cleanupRef = useRef<(() => void) | null>(null)
  useEffect(() => () => cleanupRef.current?.(), [])
  const clamp = (value: number) => Math.min(max, Math.max(min, Math.round(value)))

  const startResize = (event: ReactPointerEvent<HTMLSpanElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    event.stopPropagation()
    cleanupRef.current?.()
    const startX = event.clientX
    const pointerId = event.pointerId
    let latestWidth = width
    const move = (next: PointerEvent) => {
      if (next.pointerId !== pointerId) return
      latestWidth = clamp(width + next.clientX - startX)
      onPreview(latestWidth)
    }
    const cleanup = () => {
      document.removeEventListener("pointermove", move)
      document.removeEventListener("pointerup", finish)
      document.removeEventListener("pointercancel", cancel)
      window.removeEventListener("blur", cancel)
      cleanupRef.current = null
    }
    const finish = (next: PointerEvent) => {
      if (next.pointerId !== pointerId) return
      cleanup()
      onCommit(latestWidth)
    }
    const cancel = () => { cleanup(); onPreview(null) }
    cleanupRef.current = cleanup
    document.addEventListener("pointermove", move)
    document.addEventListener("pointerup", finish)
    document.addEventListener("pointercancel", cancel)
    window.addEventListener("blur", cancel)
  }

  return <span
    role="separator"
    tabIndex={0}
    aria-orientation="vertical"
    aria-label={`调整${label}列宽`}
    aria-valuemin={min}
    aria-valuemax={max}
    aria-valuenow={width}
    title="拖动调整列宽，双击恢复默认；方向键微调"
    className="absolute inset-y-0 right-0 z-50 w-3 cursor-col-resize touch-none select-none after:absolute after:inset-y-2 after:right-1 after:w-px after:bg-border hover:bg-primary/10 hover:after:bg-primary focus-visible:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
    onPointerDown={startResize}
    onClick={(event) => event.stopPropagation()}
    onDoubleClick={(event) => { event.stopPropagation(); onCommit(defaultWidth) }}
    onKeyDown={(event) => {
      const step = event.shiftKey ? 32 : 8
      const next = event.key === "ArrowLeft" ? width - step
        : event.key === "ArrowRight" ? width + step
          : event.key === "Home" ? defaultWidth : null
      if (next === null) return
      event.preventDefault()
      event.stopPropagation()
      onCommit(clamp(next))
    }}
  />
}
