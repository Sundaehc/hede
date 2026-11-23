"use client"

import { useEffect, useId, useRef, useState } from "react"
import { ExternalLink, ImageOff, X, ZoomIn } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type PhotoItem = {
  sku: string
  product_name: string | null
  color: string | null
  image_url?: string | null
}

function StockPhotoPreview({
  src,
  sku,
  label,
  onClose,
}: {
  src: string
  sku: string
  label: string
  onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    // Stay inside the parent dialog's focus scope while appearing above it.
    element.showModal()
    const overflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      element.close()
      document.body.style.overflow = overflow
    }
  }, [])

  const close = () => {
    dialog.current?.close()
    onClose()
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      className="fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-5xl overflow-auto rounded-2xl border border-border bg-card p-0 text-card-foreground shadow-2xl backdrop:bg-black/65"
      onCancel={(event) => {
        event.preventDefault()
        close()
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") event.stopPropagation()
      }}
      onClick={(event) => {
        event.stopPropagation()
        if (event.target === event.currentTarget) close()
      }}
    >
      <header className="flex items-center gap-2 border-b px-4 py-3 sm:gap-3 sm:px-5">
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="text-sm font-semibold sm:text-base">
            原图预览
          </h2>
          <p
            id={descriptionId}
            className="mt-0.5 text-xs wrap-anywhere text-muted-foreground"
          >
            <span className="font-mono">{sku}</span>
            {label !== sku && ` · ${label}`}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          aria-label="关闭原图预览"
          autoFocus
          onClick={close}
        >
          <X aria-hidden="true" />
        </Button>
      </header>
      <div className="grid min-h-44 place-items-center bg-muted/40 p-3 sm:p-6">
        {failed ? (
          <p
            role="status"
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <ImageOff className="size-4" aria-hidden="true" />
            图片加载失败
          </p>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={`${label}商品原图`}
            decoding="async"
            className="max-h-[min(68dvh,48rem)] max-w-full rounded-lg bg-white object-contain"
            onError={() => setFailed(true)}
          />
        )}
      </div>
      <footer className="flex justify-end border-t px-4 py-2 sm:px-5">
        <Button asChild variant="ghost" size="sm">
          <a href={src} target="_blank" rel="noopener noreferrer">
            <ExternalLink aria-hidden="true" />
            在新标签页打开原图
          </a>
        </Button>
      </footer>
    </dialog>
  )
}

export function StockProductPhoto({
  item,
  detail = false,
}: {
  item: PhotoItem
  detail?: boolean
}) {
  const path = item.image_url
  const src = path?.startsWith("/images/serve/") ? `/api${path}` : null
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const [previewSrc, setPreviewSrc] = useState<string | null>(null)
  const label = [item.product_name || item.sku, item.color]
    .filter(Boolean)
    .join(" · ")
  const frame = cn(
    "relative grid shrink-0 place-items-center overflow-hidden rounded-lg border border-border/80 bg-muted/50 text-muted-foreground",
    detail ? "size-16 sm:size-20" : "size-12"
  )

  return (
    <>
      {src && failedSrc !== src ? (
        <button
          type="button"
          aria-label={`查看原图 ${item.sku}`}
          title="查看原图"
          aria-haspopup="dialog"
          className={cn(
            frame,
            "group cursor-zoom-in outline-none hover:border-ring focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          )}
          onClick={(event) => {
            event.stopPropagation()
            setPreviewSrc(src)
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={`${label}商品图`}
            width={detail ? 80 : 48}
            height={detail ? 80 : 48}
            loading={detail ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={detail ? "auto" : "low"}
            className="absolute inset-0 size-full bg-white object-contain p-0.5"
            onError={() => setFailedSrc(src)}
          />
          <ZoomIn
            aria-hidden="true"
            className="pointer-events-none absolute right-0.5 bottom-0.5 size-4 rounded bg-black/70 p-0.5 text-white opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
          />
        </button>
      ) : (
        <span
          className={frame}
          title={`${label}暂无商品图`}
          role="img"
          aria-label={`${label}暂无商品图`}
        >
          <ImageOff
            className={detail ? "size-5" : "size-4"}
            aria-hidden="true"
          />
        </span>
      )}
      {previewSrc && (
        <StockPhotoPreview
          src={previewSrc}
          sku={item.sku}
          label={label}
          onClose={() => setPreviewSrc(null)}
        />
      )}
    </>
  )
}
