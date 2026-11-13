"use client"

import { useState } from "react"
import { ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react"

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import type { PostedProductChangeWarning } from "@/lib/posted-product-change"

const PAGE_SIZE = 10

export function PostedProductChangeDialog({ warning, saving, error, onConfirm, onCancel }: {
  warning: PostedProductChangeWarning
  saving: boolean
  error: string | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const [page, setPage] = useState(1)
  const pages = Math.max(1, Math.ceil(warning.documents.length / PAGE_SIZE))
  const documents = warning.documents.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  return <AlertDialog open onOpenChange={(open) => { if (!open && !saving) onCancel() }}>
    <AlertDialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
      <AlertDialogHeader>
        <AlertDialogTitle className="flex items-center gap-2"><span className="rounded-lg bg-amber-500/10 p-2 text-amber-700 dark:text-amber-300"><TriangleAlert className="size-5" /></span>该商品已过账，是否继续变更？</AlertDialogTitle>
        <AlertDialogDescription>该商品已出现在以下 {warning.document_count} 张经营历程已完成单据中，涉及 {warning.detail_count} 条明细。请核对本次变更及关联单据。</AlertDialogDescription>
      </AlertDialogHeader>
      <div className="overflow-hidden rounded-lg border border-amber-500/25 bg-amber-500/5 text-sm">
        {warning.changes.map((change) => <div key={change.field} className="grid grid-cols-[5rem_1fr_auto_1fr] items-start gap-3 px-4 py-3 not-first:border-t not-first:border-amber-500/15"><span className="text-muted-foreground">{change.label}</span><span className="min-w-0 break-all">{change.before || "未填写"}</span><span className="text-muted-foreground">→</span><span className="min-w-0 break-all font-medium">{change.after || "未填写"}</span></div>)}
      </div>
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="overflow-x-auto"><table className="w-full min-w-[440px] text-sm"><thead className="bg-muted/50 text-xs text-muted-foreground"><tr><th className="px-3 py-2 text-left font-medium">单据编号</th><th className="px-3 py-2 text-left font-medium">单据类型</th><th className="px-3 py-2 text-left font-medium">单据日期</th><th className="px-3 py-2 text-right font-medium">关联明细</th></tr></thead><tbody className="divide-y divide-border">{documents.map((document) => <tr key={document.id}><td className="px-3 py-2.5 font-medium break-all">{document.document_number || `单据 #${document.id}`}</td><td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground">{document.document_type || "—"}</td><td className="whitespace-nowrap px-3 py-2.5 text-muted-foreground tabular-nums">{document.date || "—"}</td><td className="px-3 py-2.5 text-right tabular-nums">{document.detail_count}</td></tr>)}</tbody></table></div>
        {pages > 1 && <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted-foreground"><span>全部 {warning.document_count} 张单据</span><div className="flex items-center gap-2"><Button type="button" size="icon-sm" variant="ghost" aria-label="上一页单据" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft className="size-4" /></Button><span className="tabular-nums">{page} / {pages}</span><Button type="button" size="icon-sm" variant="ghost" aria-label="下一页单据" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}><ChevronRight className="size-4" /></Button></div></div>}
      </div>
      <p className="text-xs leading-6 text-muted-foreground">继续后将保存商品档案变更，并按现有规则同步关联信息。取消后保留当前编辑内容，不保存本次修改。</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <AlertDialogFooter>
        <AlertDialogCancel disabled={saving} onClick={onCancel}>返回修改</AlertDialogCancel>
        <AlertDialogAction disabled={saving} onClick={(event) => { event.preventDefault(); onConfirm() }}>{saving ? "保存中…" : "继续变更"}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
}
