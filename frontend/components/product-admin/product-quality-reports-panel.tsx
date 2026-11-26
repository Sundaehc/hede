"use client"

import { useEffect, useState } from "react"
import { FileImage, FileSpreadsheet, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getProductQualityReports, productQualityReportUrl } from "@/lib/api"
import type { QualityReportList } from "@/lib/product-quality-reports"
import { cn } from "@/lib/utils"

const modifiedDate = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
})

function reportAppearance(fileName: string) {
  const extension = fileName.split(".").at(-1)?.toLowerCase()
  switch (extension) {
    case "pdf":
      return { Icon: FileText, tone: "bg-red-500 text-white", preview: true }
    case "xlsx":
    case "xls":
      return {
        Icon: FileSpreadsheet,
        tone: "bg-emerald-600 text-white",
        preview: false,
      }
    case "doc":
    case "docx":
      return { Icon: FileText, tone: "bg-blue-600 text-white", preview: false }
    case "png":
    case "jpg":
    case "jpeg":
      return {
        Icon: FileImage,
        tone: "bg-violet-600 text-white",
        preview: true,
      }
    default:
      return {
        Icon: FileText,
        tone: "bg-muted text-muted-foreground",
        preview: false,
      }
  }
}

export function ProductQualityReportsPanel({
  brand,
  productId,
}: {
  brand: string
  productId: number
}) {
  const [data, setData] = useState<QualityReportList | null>(null)
  const [error, setError] = useState("")
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getProductQualityReports(brand, productId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setError(error instanceof Error ? error.message : "读取质检报告失败")
      })
    return () => controller.abort()
  }, [brand, productId, attempt])

  return (
    <section
      aria-label="质检报告列表"
      className="rounded-xl border border-border/70 bg-card p-3 shadow-xs sm:p-4"
    >
      <h3 className="mb-3 text-sm font-semibold">质检报告</h3>
      {error ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/25 px-3 py-3">
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setError("")
              setAttempt((value) => value + 1)
            }}
          >
            重试
          </Button>
        </div>
      ) : !data ? (
        <p
          role="status"
          className="rounded-lg border bg-muted/25 px-3 py-4 text-sm text-muted-foreground"
        >
          正在读取质检报告…
        </p>
      ) : data.items.length ? (
        <ul
          aria-label="报告文件"
          className="max-h-[min(23rem,55svh)] space-y-2 overflow-y-auto pr-1 [scrollbar-gutter:stable]"
        >
          {data.items.map((item) => {
            const fileName = item.file_name ?? item.name
            const { Icon, tone, preview } = reportAppearance(fileName)
            const url = item.file_name
              ? productQualityReportUrl(brand, productId, item.id)
              : null
            const download = item.file_name
              ? productQualityReportUrl(brand, productId, item.id, true)
              : null
            return (
              <li
                key={item.id}
                className="rounded-lg border border-border/65 bg-muted/25"
              >
                <div className="grid min-h-[3.5rem] grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5 px-2.5 py-2 sm:gap-x-3 sm:px-3">
                  <span
                    className={cn(
                      "flex size-8 items-center justify-center rounded-md",
                      tone
                    )}
                    aria-hidden="true"
                  >
                    <Icon className="size-4" />
                  </span>
                  <div className="min-w-0 space-y-0.5">
                    {url && preview ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={fileName}
                        className="block w-fit max-w-full rounded-sm text-sm leading-5 font-medium wrap-anywhere hover:text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {fileName}
                      </a>
                    ) : (
                      <p className="text-sm leading-5 font-medium wrap-anywhere">
                        {fileName}
                      </p>
                    )}
                    {item.modified_at && (
                      <time
                        dateTime={item.modified_at}
                        title="文件修改时间（北京时间）"
                        className="block text-xs text-muted-foreground tabular-nums"
                      >
                        {modifiedDate.format(new Date(item.modified_at))}
                      </time>
                    )}
                    {!url && (
                      <p className="text-xs text-muted-foreground">
                        {item.status === "ambiguous"
                          ? "有多个候选，待核对"
                          : "未找到原件"}
                      </p>
                    )}
                  </div>
                  {download && (
                    <Button
                      asChild
                      variant="ghost"
                      size="sm"
                      className="text-primary hover:text-primary"
                    >
                      <a
                        href={download}
                        download={item.file_name ?? undefined}
                        aria-label={`下载 ${fileName}`}
                      >
                        下载
                      </a>
                    </Button>
                  )}
                </div>
                {item.sources.length > 0 && (
                  <details className="pr-3 pb-2 pl-[3.25rem] text-xs text-muted-foreground sm:pl-14">
                    <summary className="w-fit cursor-pointer rounded-sm underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring">
                      汇总表来源
                    </summary>
                    {item.status === "number_match" && (
                      <p className="mt-1 wrap-anywhere">
                        按报告编号匹配 · {item.name}
                      </p>
                    )}
                    <ul className="mt-1 list-disc space-y-0.5 pl-4">
                      {item.sources.map((source) => (
                        <li
                          key={JSON.stringify(source)}
                          className="wrap-anywhere"
                        >
                          {source.workbook} · {source.sheet} · 第 {source.row}{" "}
                          行
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="rounded-lg border bg-muted/25 px-3 py-4 text-sm text-muted-foreground">
          {data.original_sku
            ? `汇总表中暂无原始货号 ${data.original_sku} 的质检报告。`
            : "商品档案缺少原始货号，暂无法关联质检报告。"}
        </p>
      )}
    </section>
  )
}
