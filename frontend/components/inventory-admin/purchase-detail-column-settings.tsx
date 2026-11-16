"use client"

import { useRef, useState } from "react"
import { ArrowDown, ArrowUp, GripVertical, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER,
  PURCHASE_DETAIL_COLUMNS,
  movePurchaseDetailColumn,
  type PurchaseDetailColumnKey,
} from "@/lib/purchase-detail-columns"

export function PurchaseDetailColumnSettings({
  order,
  onApply,
  onClose,
}: {
  order: PurchaseDetailColumnKey[]
  onApply: (order: PurchaseDetailColumnKey[]) => void
  onClose: () => void
}) {
  const [draft, setDraft] = useState(order)
  const [dragging, setDragging] = useState<PurchaseDetailColumnKey | null>(null)
  const [over, setOver] = useState<PurchaseDetailColumnKey | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const move = (
    source: PurchaseDetailColumnKey,
    target: PurchaseDetailColumnKey
  ) => setDraft((current) => movePurchaseDetailColumn(current, source, target))

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>明细字段位置</DialogTitle>
          <DialogDescription>
            拖拽调整字段从左到右的位置，也可使用上下移按钮。尺码数量整组移动，组内顺序保持不变。
          </DialogDescription>
        </DialogHeader>
        <div
          ref={scrollRef}
          className="max-h-[55vh] space-y-1.5 overflow-y-auto overscroll-contain pr-1"
          aria-label="明细字段顺序"
        >
          {draft.map((key, index) => {
            const label = PURCHASE_DETAIL_COLUMNS.find(
              (column) => column.key === key
            )!.label
            return (
              <div
                key={key}
                draggable
                data-column-key={key}
                onDragStart={(event) => {
                  setDragging(key)
                  event.dataTransfer.effectAllowed = "move"
                  event.dataTransfer.setData("text/plain", key)
                }}
                onDragOver={(event) => {
                  if (!dragging) return
                  event.preventDefault()
                  setOver(key)
                  const container = scrollRef.current
                  if (container) {
                    const bounds = container.getBoundingClientRect()
                    if (event.clientY < bounds.top + 40)
                      container.scrollTop -= 24
                    if (event.clientY > bounds.bottom - 40)
                      container.scrollTop += 24
                  }
                }}
                onDrop={(event) => {
                  event.preventDefault()
                  if (dragging) move(dragging, key)
                  setDragging(null)
                  setOver(null)
                }}
                onDragEnd={() => {
                  setDragging(null)
                  setOver(null)
                }}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${over === key ? "border-primary bg-primary/5" : "border-border bg-muted/20"} ${dragging === key ? "opacity-50" : ""}`}
              >
                <GripVertical
                  className="size-4 shrink-0 cursor-grab text-muted-foreground"
                  aria-hidden="true"
                />
                <span className="w-5 text-xs text-muted-foreground tabular-nums">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 text-sm">{label}</span>
                <div className="flex gap-0.5">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    disabled={index === 0}
                    aria-label={`上移${label}`}
                    onClick={() => move(key, draft[index - 1])}
                  >
                    <ArrowUp className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    disabled={index === draft.length - 1}
                    aria-label={`下移${label}`}
                    onClick={() => move(key, draft[index + 1])}
                  >
                    <ArrowDown className="size-3.5" />
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button
            variant="ghost"
            onClick={() => setDraft(DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER)}
          >
            <RotateCcw className="size-4" />
            恢复默认
          </Button>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button onClick={() => onApply(draft)}>应用顺序</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
