"use client"

import { useId, useRef, useState, type DragEvent } from "react"
import { Check, FileSpreadsheet, Upload, X } from "lucide-react"

import { Label } from "@/components/ui/label"
import { INVENTORY_IMPORT_MAX_FILE_BYTES } from "@/lib/upload-limits.mjs"
import { cn } from "@/lib/utils"

type InventoryImportUploadProps = {
  file: File | null
  disabled?: boolean
  onFileChange: (file: File | null) => void
}

function formatFileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? (bytes / 1024 / 1024).toFixed(2) + " MB"
    : Math.max(1, Math.ceil(bytes / 1024)) + " KB"
}

export function InventoryImportUpload({
  file,
  disabled = false,
  onFileChange,
}: InventoryImportUploadProps) {
  const inputId = useId()
  const hintId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const dragDepthRef = useRef(0)
  const [dragging, setDragging] = useState(false)

  function resetDrag() {
    dragDepthRef.current = 0
    setDragging(false)
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    if (disabled || !event.dataTransfer.types.includes("Files")) return
    dragDepthRef.current += 1
    setDragging(true)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    resetDrag()
    if (!disabled && event.dataTransfer.files.length)
      onFileChange(event.dataTransfer.files[0])
  }

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor={inputId} className="text-sm font-medium">
          Excel 文件
        </Label>
        <span id={hintId} className="text-[11px] text-muted-foreground">
          单个文件不超过 {INVENTORY_IMPORT_MAX_FILE_BYTES / 1024 / 1024}MB
        </span>
      </div>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept=".xlsx,.xls,.xlsm"
        aria-describedby={hintId}
        disabled={disabled}
        className="sr-only"
        tabIndex={-1}
        onChange={(event) => {
          if (event.target.files?.[0]) onFileChange(event.target.files[0])
          event.currentTarget.value = ""
        }}
      />
      <div
        onDragEnter={handleDragEnter}
        onDragOver={(event) => {
          event.preventDefault()
          event.stopPropagation()
          event.dataTransfer.dropEffect = disabled ? "none" : "copy"
        }}
        onDragLeave={(event) => {
          event.preventDefault()
          event.stopPropagation()
          dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
          if (!dragDepthRef.current) setDragging(false)
        }}
        onDrop={handleDrop}
        className={cn(
          "relative flex items-center rounded-xl border border-dashed transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20",
          dragging && !disabled
            ? "border-primary bg-primary/5 ring-3 ring-primary/10"
            : file
              ? "border-primary/25 bg-primary/[0.025]"
              : "border-border bg-muted/20 hover:border-foreground/30 hover:bg-muted/40",
          disabled && "opacity-60"
        )}
      >
        <button
          type="button"
          aria-label={file ? "更换 Excel 文件" : "选择 Excel 文件"}
          aria-describedby={hintId}
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "flex min-w-0 flex-1 cursor-pointer rounded-xl outline-none disabled:cursor-not-allowed",
            file
              ? "items-center gap-3 p-4 text-left"
              : "min-h-40 flex-col items-center justify-center px-4 py-5 text-center"
          )}
        >
          <span
            className={cn(
              "flex size-11 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-background text-foreground shadow-xs",
              !file && "mb-3"
            )}
          >
            {file ? (
              <FileSpreadsheet className="size-5" aria-hidden="true" />
            ) : (
              <Upload className="size-5" aria-hidden="true" />
            )}
          </span>
          {file ? (
            <span className="min-w-0 flex-1 space-y-1">
              <span
                className="block truncate text-sm font-medium"
                title={file.name}
              >
                {file.name}
              </span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <span>{formatFileSize(file.size)}</span>
                <span aria-hidden="true">·</span>
                <span>点击或拖入文件替换</span>
              </span>
            </span>
          ) : (
            <>
              <span className="text-sm font-medium">
                {dragging ? "松开即可添加文件" : "拖拽 Excel 文件到此处"}
              </span>
              <span className="mt-1 text-xs text-muted-foreground">
                或
                <span className="mx-1 font-medium text-foreground underline decoration-border underline-offset-4">
                  点击选择文件
                </span>
                ，支持 .xlsx / .xls / .xlsm
              </span>
            </>
          )}
        </button>
        {file && (
          <div className="flex shrink-0 items-center gap-2 pr-3">
            <span className="hidden items-center gap-1 rounded-full bg-background px-2 py-1 text-[11px] text-muted-foreground sm:inline-flex">
              <Check className="size-3" aria-hidden="true" />
              已选择
            </span>
            <button
              type="button"
              aria-label="移除已选文件"
              disabled={disabled}
              onClick={() => {
                resetDrag()
                onFileChange(null)
              }}
              className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors outline-none hover:bg-destructive/10 hover:text-destructive focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
