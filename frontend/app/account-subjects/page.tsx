"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronRight, Edit, History, Plus, Search, Trash2, X } from "lucide-react"

import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  ApiError,
  createInventoryAccountSubject,
  deleteInventoryAccountSubject,
  listInventoryAccountSubjects,
  updateInventoryAccountSubject,
  type AccountSubjectCategory,
  type InventoryAccountSubject,
} from "@/lib/api"

const ACCOUNT_SUBJECT_CATEGORIES: AccountSubjectCategory[] = ["收入类", "支出类"]

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function AccountSubjectsPage() {
  const [items, setItems] = useState<InventoryAccountSubject[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [selectedCategory, setSelectedCategory] = useState<AccountSubjectCategory>("收入类")
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")

  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState("")
  const [category, setCategory] = useState<AccountSubjectCategory>("收入类")
  const [isSaving, setIsSaving] = useState(false)

  const [editTarget, setEditTarget] = useState<InventoryAccountSubject | null>(null)
  const [editName, setEditName] = useState("")
  const [editCategory, setEditCategory] = useState<AccountSubjectCategory>("收入类")
  const [editConfirmOpen, setEditConfirmOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<InventoryAccountSubject | null>(null)

  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({ title: "", description: "" })

  const showMessage = (title: string, description: string) => {
    setMessageContent({ title, description })
    setMessageOpen(true)
  }

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await listInventoryAccountSubjects()
      setItems(response.items)
    } catch (error) {
      setItems([])
      showMessage("加载失败", getErrorMessage(error))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [load])

  const filteredCategories = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return ACCOUNT_SUBJECT_CATEGORIES
    return ACCOUNT_SUBJECT_CATEGORIES.filter((subjectCategory) => (
      subjectCategory.toLowerCase().includes(term)
      || items.some((item) => (
        (item.category || "收入类") === subjectCategory
        && item.name.toLowerCase().includes(term)
      ))
    ))
  }, [items, query])

  const activeCategory = filteredCategories.includes(selectedCategory)
    ? selectedCategory
    : filteredCategories[0] ?? null

  const visibleItems = useMemo(() => (
    activeCategory
      ? items.filter((item) => (item.category || "收入类") === activeCategory)
      : []
  ), [activeCategory, items])

  const categoryCount = (subjectCategory: AccountSubjectCategory) => (
    items.filter((item) => (item.category || "收入类") === subjectCategory).length
  )

  const openCreate = () => {
    if (!activeCategory) return
    setName("")
    setCategory(activeCategory)
    setCreateOpen(true)
  }

  const handleCreate = async () => {
    const nextName = name.trim()
    if (!nextName) return showMessage("新增失败", "科目名称不能为空")
    setIsSaving(true)
    try {
      await createInventoryAccountSubject({ code: "", category, name: nextName })
      setCreateOpen(false)
      setSelectedCategory(category)
      await load()
    } catch (error) {
      showMessage("新增失败", getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  const openEdit = (item: InventoryAccountSubject) => {
    setEditTarget(item)
    setEditName(item.name)
    setEditCategory(item.category || "收入类")
  }

  const requestUpdate = () => {
    if (!editTarget) return
    const nextName = editName.trim()
    if (!nextName) return showMessage("保存失败", "科目名称不能为空")
    if (nextName === editTarget.name.trim() && editCategory === (editTarget.category || "收入类")) {
      setEditTarget(null)
      return
    }
    setEditConfirmOpen(true)
  }

  const saveUpdate = async () => {
    if (!editTarget) return
    setIsSaving(true)
    try {
      const response = await updateInventoryAccountSubject(editTarget.id, {
        category: editCategory,
        name: editName.trim(),
      })
      setEditConfirmOpen(false)
      setEditTarget(null)
      setSelectedCategory(editCategory)
      await load()
      showMessage("保存成功", response.message)
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setIsSaving(true)
    try {
      await deleteInventoryAccountSubject(deleteTarget.id)
      setDeleteTarget(null)
      await load()
    } catch (error) {
      showMessage("删除失败", getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  const editNameChanged = Boolean(editTarget && editName.trim() !== editTarget.name.trim())

  return (
    <div className="app-page">
      <div className="app-content">
        <div className="page-header">
          <div className="flex items-center gap-3">
            <h1 className="page-title">科目管理</h1>
            <span className="rounded-full border border-border bg-muted/45 px-3 py-1 text-sm text-muted-foreground tabular-nums">
              {items.length} 个科目
            </span>
          </div>
          <Button size="sm" variant="outline" onClick={() => setOperationLogOpen(true)} className="cursor-pointer">
            <History className="h-4 w-4" />
            <span className="ml-1.5">操作日志</span>
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <section className="surface-panel p-4">
            <p className="text-sm font-medium text-foreground">科目分类</p>
            <form
              className="mt-3 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault()
                setQuery(queryInput.trim())
              }}
            >
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  placeholder="搜索分类或科目"
                  className="pl-9"
                />
              </div>
              {(query || queryInput) && (
                <Button
                  type="button"
                  size="icon"
                  variant="outline"
                  className="cursor-pointer"
                  aria-label="清空搜索"
                  onClick={() => { setQuery(""); setQueryInput("") }}
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </form>

            <div className="mt-3 space-y-1.5">
              {isLoading && (
                <div className="rounded-xl border border-border bg-card px-3 py-10 text-center text-sm text-muted-foreground">加载中...</div>
              )}
              {!isLoading && filteredCategories.length === 0 && (
                <div className="rounded-xl border border-border bg-card px-3 py-10 text-center text-sm text-muted-foreground">暂无匹配分类</div>
              )}
              {!isLoading && filteredCategories.map((subjectCategory) => {
                const selected = subjectCategory === activeCategory
                return (
                  <button
                    key={subjectCategory}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setSelectedCategory(subjectCategory)}
                    className={`group relative flex w-full cursor-pointer items-center gap-2 overflow-hidden rounded-xl border px-3 py-3 text-left text-sm shadow-xs transition-all duration-150 ${selected ? "border-foreground bg-muted/70 shadow-sm ring-1 ring-foreground/10" : "border-border bg-card hover:-translate-y-px hover:border-foreground/25 hover:bg-muted/45 hover:shadow-sm"}`}
                  >
                    <span aria-hidden="true" className={`absolute inset-y-2 left-0 w-1 rounded-r-full bg-foreground ${selected ? "opacity-100" : "opacity-0 group-hover:opacity-25"}`} />
                    <span className="min-w-0 flex-1 truncate font-medium text-foreground">{subjectCategory}</span>
                    <span className={`flex shrink-0 items-center gap-1.5 rounded-full px-1.5 py-0.5 text-xs ${selected ? "bg-background text-foreground shadow-xs" : "text-muted-foreground"}`}>
                      <span>{categoryCount(subjectCategory)} 个</span>
                      <ChevronRight className="h-4 w-4" />
                    </span>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="surface-panel p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-foreground">{activeCategory || "请选择科目分类"}</p>
                  {activeCategory && (
                    <span className="rounded-full border border-border bg-muted/45 px-2.5 py-0.5 text-xs text-muted-foreground tabular-nums">
                      {visibleItems.length} 个科目
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">选择分类后维护其下科目</p>
              </div>
              <Button size="sm" onClick={openCreate} disabled={!activeCategory} className="cursor-pointer">
                <Plus className="h-4 w-4" />
                <span className="ml-1.5">新增科目</span>
              </Button>
            </div>

            <div className="mt-3 table-panel overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="table-head-row">
                      <th className="px-4 py-3 font-medium">科目名称</th>
                      <th className="w-32 px-4 py-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {isLoading && <tr><td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">加载中...</td></tr>}
                    {!isLoading && !activeCategory && <tr><td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">请选择科目分类</td></tr>}
                    {!isLoading && activeCategory && visibleItems.length === 0 && <tr><td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">该分类暂无科目</td></tr>}
                    {!isLoading && visibleItems.map((item) => (
                      <tr key={item.id} className="table-row">
                        <td className="px-4 py-2.5 font-medium">{item.name}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-0.5">
                            <Button variant="ghost" size="icon" onClick={() => openEdit(item)} disabled={isSaving} className="cursor-pointer" aria-label={`编辑科目 ${item.name}`}>
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(item)} disabled={isSaving} className="cursor-pointer" aria-label={`删除科目 ${item.name}`}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>新增科目</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="create-subject-category">所属分类 *</Label>
              <Input id="create-subject-category" value={category} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="create-subject-name">科目名称 *</Label>
              <Input
                id="create-subject-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    void handleCreate()
                  }
                }}
                placeholder="例如：罚款收入"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={isSaving} className="cursor-pointer">取消</Button>
            <Button onClick={handleCreate} disabled={isSaving} className="cursor-pointer">{isSaving ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editTarget !== null}
        onOpenChange={(open) => {
          if (!open && !isSaving && !editConfirmOpen) setEditTarget(null)
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>编辑科目</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="edit-subject-category">所属分类 *</Label>
              <select
                id="edit-subject-category"
                value={editCategory}
                onChange={(event) => setEditCategory(event.target.value as AccountSubjectCategory)}
                className="flex h-9 w-full cursor-pointer rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/35"
              >
                {ACCOUNT_SUBJECT_CATEGORIES.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-subject-name">科目名称 *</Label>
              <Input
                id="edit-subject-name"
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    requestUpdate()
                  }
                }}
                placeholder="请输入科目名称"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)} disabled={isSaving} className="cursor-pointer">取消</Button>
            <Button onClick={requestUpdate} disabled={isSaving} className="cursor-pointer">{isSaving ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={editConfirmOpen}
        title="确认修改科目"
        description={editNameChanged
          ? `将科目“${editTarget?.name || ""}”修改为“${editName.trim()}”（${editCategory}），会同步更新对应的历史经营历程明细，请确定是否修改。`
          : `确定将科目“${editTarget?.name || ""}”移动到“${editCategory}”？历史经营历程明细不会被改动。`}
        confirmLabel={isSaving ? "修改中..." : "确认修改"}
        onConfirm={() => void saveUpdate()}
        onCancel={() => setEditConfirmOpen(false)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除科目"
        description={`确定删除科目 ${deleteTarget?.name || ""}？已保存的单据明细不会被改动。`}
        confirmLabel={isSaving ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <MessageDialog open={messageOpen} title={messageContent.title} description={messageContent.description} onClose={() => setMessageOpen(false)} />
      <OperationLogDialog module="account_subject" title="科目管理操作日志" open={operationLogOpen} onOpenChange={setOperationLogOpen} />
    </div>
  )
}
