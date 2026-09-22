"use client"

import { useCallback, useEffect, useId, useRef, useState } from "react"
import { ArrowLeft, Check, Copy, History, LoaderCircle, RefreshCw, Sparkles, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { getProductCopywritingHistoryVersion, getSavedProductCopywriting, regenerateProductCopywriting, type ProductCopywritingHistoryVersion, type SavedProductCopywriting } from "@/lib/api"
import type { ProductListItem } from "@/lib/types"
import { ProductCopywritingHistory } from "./product-copywriting-history"

type ProductCopywritingDialogProps = {
  item: ProductListItem
  onClose: () => void
}

const MAX_PROMPT_LENGTH = 30_000

export function ProductCopywritingDialog({ item, onClose }: ProductCopywritingDialogProps) {
  const [saved, setSaved] = useState<SavedProductCopywriting | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyVersion, setHistoryVersion] = useState<ProductCopywritingHistoryVersion | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const historyRequest = useRef(0)
  const result = historyVersion ?? saved?.item ?? null
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState(false)
  const [promptDraft, setPromptDraft] = useState("")
  const promptEditedRef = useRef(false)
  const promptId = useId()
  const requestVersion = useRef(0)
  const contentRef = useRef<HTMLDivElement>(null)
  const loadingRef = useRef(false)
  const regenerateRef = useRef(false)
  const isGenerating = regenerating || saved?.status === "pending" || saved?.status === "running"
  const hasPrompt = typeof saved?.input_prompt === "string"
  const promptChanged = hasPrompt && promptDraft !== saved.input_prompt
  const promptInvalid = hasPrompt && (!promptDraft.trim() || Array.from(promptDraft).length > MAX_PROMPT_LENGTH)
  const sections = result?.content.split(/(?=【(?:主标题|副标题|主文案|卖点|图片建议|风险校对)】)/).filter((section) => section.trim()) ?? []
  const riskReviewStart = result?.content.indexOf("【风险校对】") ?? -1
  const copyContent = result
    ? (riskReviewStart >= 0 ? result.content.slice(0, riskReviewStart) : result.content).trim()
    : ""

  const load = useCallback(async (silent = false) => {
    if (regenerateRef.current) return
    const version = ++requestVersion.current
    loadingRef.current = true
    if (!silent) setLoading(true)
    setError(null)
    setCopied(false)
    setCopyError(null)
    try {
      const response = await getSavedProductCopywriting(item.brand, item.id)
      if (version === requestVersion.current) {
        setSaved(response)
        if (!promptEditedRef.current) setPromptDraft(response.input_prompt ?? "")
      }
    } catch (loadError) {
      if (version === requestVersion.current) {
        setError(loadError instanceof Error ? loadError.message : "读取失败，请稍后重试")
      }
    } finally {
      if (version === requestVersion.current) {
        loadingRef.current = false
        setLoading(false)
      }
    }
  }, [item.brand, item.id])

  useEffect(() => {
    setSaved(null)
    setHistoryOpen(false)
    setHistoryVersion(null)
    setHistoryLoading(false)
    setHistoryError(null)
    setPromptDraft("")
    promptEditedRef.current = false
    regenerateRef.current = false
    setRegenerating(false)
    void load()
    return () => { requestVersion.current += 1; historyRequest.current += 1 }
  }, [load])

  useEffect(() => {
    if (regenerating || loading || error || (saved?.status !== "running" && saved?.status !== "pending")) return
    const timer = window.setTimeout(() => { void load(true) }, 3000)
    return () => window.clearTimeout(timer)
  }, [saved, regenerating, loading, error, load])

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2000)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function handleCopy() {
    if (!result || !copyContent) return
    setCopyError(null)
    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(copyContent)
      } else {
        const previousFocus = document.activeElement as HTMLElement | null
        const textarea = document.createElement("textarea")
        textarea.value = copyContent
        textarea.style.position = "fixed"
        textarea.style.opacity = "0"
        contentRef.current?.appendChild(textarea)
        try {
          textarea.select()
          if (!document.execCommand("copy")) throw new Error("copy failed")
        } finally {
          textarea.remove()
          previousFocus?.focus()
        }
      }
      setCopied(true)
    } catch {
      setCopyError("自动复制失败，请选中下方文案手动复制。")
    }
  }

  async function handleRegenerate() {
    if (historyVersion || historyLoading || loadingRef.current || regenerateRef.current || isGenerating || promptInvalid) return
    regenerateRef.current = true
    const version = ++requestVersion.current
    setRegenerating(true)
    setError(null)
    setCopyError(null)
    setCopied(false)
    try {
      const response = hasPrompt
        ? await regenerateProductCopywriting(item.brand, item.id, promptDraft)
        : await regenerateProductCopywriting(item.brand, item.id)
      if (version !== requestVersion.current) return
      const submittedPrompt = response.input_prompt ?? (hasPrompt ? promptDraft : null)
      promptEditedRef.current = false
      setPromptDraft(submittedPrompt ?? "")
      setSaved((current) => ({
        status: response.status,
        item: current?.item ?? null,
        message: response.message,
        input_prompt: submittedPrompt,
        prompt_source: submittedPrompt === null ? null : "saved",
      }))
    } catch (regenerateError) {
      if (version === requestVersion.current) {
        setError(regenerateError instanceof Error ? regenerateError.message : "提交重新生成失败，请稍后重试")
      }
    } finally {
      if (version === requestVersion.current) {
        regenerateRef.current = false
        setRegenerating(false)
      }
    }
  }

  function returnToCurrent() {
    historyRequest.current += 1
    setHistoryVersion(null)
    setHistoryLoading(false)
    setHistoryError(null)
    setCopied(false)
    setCopyError(null)
  }

  async function viewHistory(historyId: number) {
    const request = ++historyRequest.current
    setHistoryLoading(true)
    setHistoryError(null)
    setCopied(false)
    setCopyError(null)
    try {
      const version = await getProductCopywritingHistoryVersion(item.brand, item.id, historyId)
      if (request === historyRequest.current) setHistoryVersion(version)
    } catch (loadError) {
      if (request === historyRequest.current) setHistoryError(loadError instanceof Error ? loadError.message : "历史版本读取失败，请重试")
    } finally {
      if (request === historyRequest.current) setHistoryLoading(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent ref={contentRef} className="flex max-h-[90vh] w-[min(960px,calc(100vw-2rem))] max-w-none flex-col overflow-hidden p-0">
        <DialogHeader className="border-b border-border px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <DialogTitle className="flex items-center gap-2 text-lg"><Sparkles className="h-5 w-5 text-primary" />生图提示词</DialogTitle>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-md bg-muted px-2 py-1 font-mono font-semibold text-foreground">{item.sku || item.original_sku || item.id}</span>
                {item.product_name ? <span className="text-muted-foreground">{item.product_name}</span> : null}
                {item.color ? <span className="text-muted-foreground">· {item.color}</span> : null}
              </div>
            </div>
            <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="关闭生图提示词" className="shrink-0 cursor-pointer"><X className="h-4 w-4" /></Button>
          </div>
        </DialogHeader>

        <div className="min-h-48 min-w-0 flex-1 overflow-y-auto px-6 py-5" aria-busy={loading || isGenerating || historyLoading}>
          {historyOpen ? <ProductCopywritingHistory key={`${item.brand}:${item.id}`} brand={item.brand} productId={item.id} selectedId={historyVersion?.id ?? null} onSelect={(id) => void viewHistory(id)} /> : null}
          {historyLoading ? <p role="status" className="mb-4 flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" />正在读取版本内容…</p> : null}
          {historyError ? <p role="alert" className="mb-4 text-sm text-destructive">{historyError}，可重新点击版本重试。</p> : null}
          {historyVersion ? (
            <section aria-label="历史版本预览" className="mb-5 rounded-xl border border-primary/20 bg-primary/5 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div><h3 className="text-sm font-semibold">历史版本 · 只读</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">查看历史不会替换当前文案或未提交的提示词草稿。</p></div>
                <Button type="button" size="sm" variant="outline" onClick={returnToCurrent}><ArrowLeft className="h-3.5 w-3.5" />返回当前版本</Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
                <span>{historyVersion.current_template ? "当前模板" : "历史模板"}</span>
                <span>模型：{historyVersion.model || "未记录"}</span>
                <span>图片来源：{{ us3: "US3", shared: "共享目录", local: "本地", unknown: "未记录" }[historyVersion.image_source]}</span>
              </div>
              <details className="mt-4 border-t border-primary/15 pt-3">
                <summary className="cursor-pointer text-sm font-medium">当时使用的生成提示词</summary>
                {historyVersion.input_prompt ? <textarea aria-label="历史生成提示词（只读）" readOnly value={historyVersion.input_prompt} rows={8} className="mt-3 max-h-80 w-full resize-y rounded-lg border border-input bg-background p-3 text-sm leading-6" /> : <p className="mt-2 text-xs text-muted-foreground">该版本未保存输入提示词，不使用当前档案补填历史。</p>}
              </details>
            </section>
          ) : null}
          {loading ? (
            <div role="status" className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 p-4 text-sm">
              <LoaderCircle className="h-5 w-5 shrink-0 animate-spin text-primary motion-reduce:animate-none" />
              <div><p className="font-medium">正在读取已保存的提示词…</p><p className="mt-1 text-xs text-muted-foreground">仅读取数据库，不触发模型生成。</p></div>
            </div>
          ) : null}
          {error ? <div role="alert" className="mb-4 rounded-lg border border-destructive/25 bg-destructive/5 p-4 text-sm text-destructive">{error}{result ? <p className="mt-2">下方保留上次读取的内容。</p> : null}</div> : null}
          {!historyVersion && !loading && saved?.message ? <div role={saved.item?.stale || saved.status === "failed" ? "alert" : "status"} className="mb-4 rounded-lg border border-border bg-muted/40 p-4 text-sm">{saved.message}</div> : null}
          {copyError ? <p role="alert" className="mb-3 text-sm text-destructive">{copyError}</p> : null}
          {!historyVersion && hasPrompt ? (
            <section className="mb-6 overflow-hidden rounded-xl border border-border bg-muted/20" aria-label="提示词编辑区">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
                <label htmlFor={promptId} className="text-sm font-semibold">生成提示词（可编辑）</label>
                <div className="flex items-center gap-3">
                  <span className={promptChanged ? "text-xs text-amber-700 dark:text-amber-400" : "text-xs text-muted-foreground"}>
                    {promptChanged ? "有未提交的修改" : saved.prompt_source === "archive" ? "根据当前档案填充" : saved.prompt_source === "previous" ? "上一版保存的提示词" : "最近一次提交的提示词"}
                  </span>
                  <Button type="button" variant="ghost" size="sm" disabled={!promptChanged || loading || isGenerating} onClick={() => {
                    setPromptDraft(saved.input_prompt ?? "")
                    promptEditedRef.current = false
                  }} className="cursor-pointer">撤销修改</Button>
                </div>
              </div>
              <div className="space-y-2 p-4">
                <p id={`${promptId}-help`} className="text-xs leading-5 text-muted-foreground">
                  {saved.prompt_source === "archive" ? "暂无已保存的输入提示词，以下根据当前档案填充，不代表历史生成输入。" : "修改后点击“重新生成”，将使用编辑后的完整提示词和商品主图；不会修改商品档案。"}
                </p>
                <textarea id={promptId} value={promptDraft} rows={10} disabled={loading || isGenerating}
                  aria-describedby={`${promptId}-help ${promptId}-length`} aria-invalid={promptInvalid}
                  onChange={(event) => {
                    setPromptDraft(event.target.value)
                    promptEditedRef.current = event.target.value !== saved.input_prompt
                  }}
                  className="max-h-[45vh] min-h-48 w-full min-w-0 resize-y rounded-lg border border-input bg-background p-3 text-sm leading-6 text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60"
                />
                <div id={`${promptId}-length`} className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                  <span className={promptInvalid ? "text-destructive" : undefined}>{promptInvalid ? "提示词不能为空，且不能超过30,000字。" : "保留真实产品信息及六个输出区块；未提交的修改关闭后不会保存。"}</span>
                  <span className="tabular-nums">{Array.from(promptDraft).length.toLocaleString("zh-CN")} / 30,000</span>
                </div>
              </div>
            </section>
          ) : null}
          {result ? (
            <div className={loading ? "mt-5 space-y-5 opacity-60" : "space-y-5"}>
              {sections.map((section, index) => {
                const heading = section.match(/^【([^】]+)】/)
                return (
                  <section key={index} className={heading?.[1] === "风险校对" ? "rounded-lg border border-amber-500/25 bg-amber-500/5 p-4" : "border-b border-border/70 pb-5 last:border-0"}>
                    {heading ? <h3 className="mb-2 text-sm font-semibold text-foreground">{heading[1]}</h3> : null}
                    <p className="whitespace-pre-wrap break-words text-sm leading-7 text-foreground/90">{heading ? section.slice(heading[0].length).trim() : section}</p>
                  </section>
                )
              })}
            </div>
          ) : null}
        </div>

        <DialogFooter className="flex flex-wrap items-center gap-3 border-t border-border bg-muted/20 px-6 py-4 sm:justify-between">
          <div className="min-w-0 text-xs leading-5 text-muted-foreground">
            <p>AI生成内容，上版前请核对产品事实与风险校对。</p>
            {result ? <p className="break-all">{new Date(result.generated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" aria-expanded={historyOpen} onClick={() => { setHistoryOpen(!historyOpen); if (historyOpen) returnToCurrent() }} className="cursor-pointer"><History className="h-4 w-4" />{historyOpen ? "收起历史" : "历史版本"}</Button>
            <Button type="button" variant="outline" disabled={loading || regenerating} onClick={() => { if (!loadingRef.current) void load() }} className="cursor-pointer"><RefreshCw className="h-4 w-4" />刷新内容</Button>
            <Button type="button" variant="outline" disabled={!!historyVersion || historyLoading || loading || isGenerating || promptInvalid} onClick={() => void handleRegenerate()} className="cursor-pointer">{isGenerating ? <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : <Sparkles className="h-4 w-4" />}{regenerating ? "提交中…" : isGenerating ? "生成中…" : "重新生成"}</Button>
            <Button type="button" disabled={!result || loading || historyLoading} onClick={() => void handleCopy()} className="cursor-pointer">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied ? "已复制" : historyVersion ? "复制此版本" : "复制全部"}</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
