"use client"

import { useEffect, useRef, useState } from "react"
import { Check, CircleAlert, Copy } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { copyTextareaText } from "@/lib/copy-textarea"

function unmatchedProducts(message: string) {
  const match = message.match(
    /^以下商品编码未匹配到商品信息档案[：:]\s*([\s\S]+?)。\s*请联系商品部维护商品信息档案后再导入；本次未导入任何数据。([\s\S]*)$/
  )
  if (!match) return null

  const totalMatch = match[1].match(/等\s*(\d+)\s*个商品编码$/)
  const codeText = totalMatch
    ? match[1].slice(0, totalMatch.index).trim()
    : match[1].trim()
  const codes = codeText.split("、").map((code) => code.trim()).filter(Boolean)
  if (!codes.length) return null

  return {
    codes,
    total: totalMatch ? Number(totalMatch[1]) : codes.length,
    extraMessage: match[2].trim(),
  }
}

export function InventoryImportError({ message }: { message: string }) {
  const products = unmatchedProducts(message)
  const copyContainerRef = useRef<HTMLDivElement>(null)
  const [copyState, setCopyState] = useState<"idle" | "copying" | "copied" | "failed">("idle")

  useEffect(() => {
    if (copyState !== "copied") return
    const timer = window.setTimeout(() => setCopyState("idle"), 2000)
    return () => window.clearTimeout(timer)
  }, [copyState])

  async function handleCopy() {
    if (!products || !copyContainerRef.current || copyState === "copying") return
    setCopyState("copying")
    const previousFocus = document.activeElement as HTMLElement | null
    const textarea = document.createElement("textarea")
    textarea.value = products.codes.join("\n")
    textarea.readOnly = true
    textarea.style.position = "fixed"
    textarea.style.opacity = "0"
    copyContainerRef.current.appendChild(textarea)
    try {
      setCopyState(await copyTextareaText(textarea) ? "copied" : "failed")
    } finally {
      textarea.remove()
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true })
    }
  }

  const truncated = Boolean(products && products.total > products.codes.length)

  return (
    <Alert className="rounded-xl border-destructive/25 bg-destructive/[0.035] p-4 dark:bg-destructive/5">
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
          <CircleAlert className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1 pt-0.5">
          <AlertTitle className="mb-0 text-sm font-semibold leading-5 text-foreground">
            {products ? "商品档案未匹配" : "导入未完成"}
          </AlertTitle>
          <AlertDescription className="mt-1 text-xs leading-5 break-words whitespace-pre-wrap">
            {products ? "本次未导入任何数据，请先核对以下商品。" : message}
          </AlertDescription>
        </div>
      </div>
      {products && (
        <div className="mt-3 space-y-3 sm:ml-11">
          <div ref={copyContainerRef} className="min-w-0 rounded-lg border border-destructive/15 bg-background/80 px-3 py-2.5">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
              <span className="text-xs text-muted-foreground">
                未匹配编码 <span className="ml-1 font-medium text-foreground tabular-nums">{products.total}</span> 个
              </span>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={handleCopy}
                aria-disabled={copyState === "copying"}
                className="text-xs text-muted-foreground"
              >
                {copyState === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
                {copyState === "copied" ? "已复制" : copyState === "copying" ? "复制中…" : truncated ? "复制已显示编码" : "复制编码"}
              </Button>
            </div>
            <ul aria-label="未匹配的商品编码" className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto overscroll-contain">
              {products.codes.map((code, index) => (
                <li key={`${index}-${code}`} className="max-w-full rounded-md border border-border/60 bg-muted/60 px-2 py-1">
                  <code className="font-mono text-xs leading-5 break-all text-foreground select-all">{code}</code>
                </li>
              ))}
            </ul>
            {truncated && <p className="mt-2 text-xs leading-5 text-muted-foreground">仅显示前 {products.codes.length} 个编码，共 {products.total} 个未匹配。</p>}
            <p role="status" className={copyState === "failed" ? "mt-2 text-xs leading-5 text-destructive" : "sr-only"}>
              {copyState === "failed" ? "复制失败，请选中编码手动复制。" : copyState === "copied" ? "商品编码已复制" : null}
            </p>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            请联系<span className="font-medium text-foreground">商品部</span>核对商品档案及条码规则，维护后重新预检查并导入。
          </p>
          {products.extraMessage && <p className="text-xs leading-5 break-words text-muted-foreground">{products.extraMessage}</p>}
        </div>
      )}
    </Alert>
  )
}
