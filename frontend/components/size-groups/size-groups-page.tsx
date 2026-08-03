"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Check, History, Loader2, Plus, Ruler, Save, Trash2 } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, createSizeGroup, deleteSizeGroup, listSizeGroups, updateSizeGroup } from "@/lib/api"
import type { SizeGroup, SizeGroupWritePayload } from "@/lib/types"
import { cn } from "@/lib/utils"


type SizeGroupItemDraft = {
  key: string
  size_name: string
  barcode: string
}

type SizeGroupDraft = {
  name: string
  items: SizeGroupItemDraft[]
}

const newDraftItem = (): SizeGroupItemDraft => ({
  key: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  size_name: "",
  barcode: "",
})

const EMPTY_DRAFT = (): SizeGroupDraft => ({ name: "", items: [newDraftItem()] })

function draftFromGroup(group: SizeGroup): SizeGroupDraft {
  return {
    name: group.name,
    items: group.items.map((item) => ({
      key: String(item.id),
      size_name: item.size_name,
      barcode: item.barcode,
    })),
  }
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return "操作失败，请稍后重试"
}

function sortedGroups(items: SizeGroup[]) {
  return [...items].sort((left, right) => left.name.localeCompare(right.name, "zh-CN"))
}

export function SizeGroupsPage() {
  const { user } = useAuth()
  const canManage = user?.role_code === "super_admin" || ["商品部", "开发部"].includes(user?.department_code ?? "")
  const [groups, setGroups] = useState<SizeGroup[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draft, setDraft] = useState<SizeGroupDraft>(EMPTY_DRAFT)
  const [isNew, setIsNew] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<SizeGroup | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [message, setMessage] = useState<{ title: string; description: string } | null>(null)

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedId) ?? null,
    [groups, selectedId],
  )

  const load = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await listSizeGroups()
      setGroups(sortedGroups(response.items))
    } catch (error) {
      setGroups([])
      setMessage({ title: "加载失败", description: getErrorMessage(error) })
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (canManage) {
      void load()
    } else {
      setIsLoading(false)
    }
  }, [canManage, load])

  useEffect(() => {
    if (isNew) return
    const nextGroup = groups.find((group) => group.id === selectedId) ?? groups[0] ?? null
    if (nextGroup) {
      if (nextGroup.id !== selectedId) setSelectedId(nextGroup.id)
      setDraft(draftFromGroup(nextGroup))
    } else {
      setSelectedId(null)
      setDraft(EMPTY_DRAFT())
    }
  }, [groups, isNew, selectedId])

  const selectGroup = (group: SizeGroup) => {
    setSelectedId(group.id)
    setIsNew(false)
    setDraft(draftFromGroup(group))
  }

  const startNew = () => {
    setSelectedId(null)
    setIsNew(true)
    setDraft(EMPTY_DRAFT())
  }

  const updateItem = (key: string, field: "size_name" | "barcode", value: string) => {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item) => item.key === key ? { ...item, [field]: value } : item),
    }))
  }

  const deleteItem = (key: string) => {
    setDraft((current) => ({
      ...current,
      items: current.items.length === 1 ? current.items : current.items.filter((item) => item.key !== key),
    }))
  }

  const buildPayload = (): SizeGroupWritePayload | null => {
    const name = draft.name.trim()
    const items = draft.items.map((item) => ({
      size_name: item.size_name.trim(),
      barcode: item.barcode.trim(),
    }))
    if (!name) {
      setMessage({ title: "保存失败", description: "尺码组名称不能为空" })
      return null
    }
    if (items.some((item) => !item.size_name || !item.barcode)) {
      setMessage({ title: "保存失败", description: "请填写每条尺码明细的尺码和条码" })
      return null
    }
    if (new Set(items.map((item) => item.size_name)).size !== items.length) {
      setMessage({ title: "保存失败", description: "同一尺码组内不能有重复尺码" })
      return null
    }
    if (new Set(items.map((item) => item.barcode)).size !== items.length) {
      setMessage({ title: "保存失败", description: "同一尺码组内不能有重复条码" })
      return null
    }
    return { name, items }
  }

  const save = async () => {
    const payload = buildPayload()
    if (!payload) return
    setIsSaving(true)
    try {
      const response = isNew || selectedId === null
        ? await createSizeGroup(payload)
        : await updateSizeGroup(selectedId, payload)
      setGroups((current) => sortedGroups([
        ...current.filter((group) => group.id !== response.item.id),
        response.item,
      ]))
      setSelectedId(response.item.id)
      setIsNew(false)
      setDraft(draftFromGroup(response.item))
    } catch (error) {
      setMessage({ title: "保存失败", description: getErrorMessage(error) })
    } finally {
      setIsSaving(false)
    }
  }

  const removeGroup = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await deleteSizeGroup(deleteTarget.id)
      setGroups((current) => current.filter((group) => group.id !== deleteTarget.id))
      setDeleteTarget(null)
      if (selectedId === deleteTarget.id) {
        setSelectedId(null)
        setIsNew(false)
      }
    } catch (error) {
      setMessage({ title: "删除失败", description: getErrorMessage(error) })
    } finally {
      setIsDeleting(false)
    }
  }

  if (!canManage) {
    return <div className="app-page"><div className="app-content py-12 text-sm text-muted-foreground">暂无访问权限</div></div>
  }

  return (
    <div className="app-page">
      <div className="app-content space-y-4">
        <div className="page-header">
          <div>
            <h1 className="page-title">尺码组管理</h1>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 items-center rounded-full border border-border bg-muted/45 px-3 text-sm text-muted-foreground">共 {groups.length} 组</div>
            <Button type="button" variant="outline" className="cursor-pointer gap-1.5" onClick={() => setOperationLogOpen(true)}>
              <History className="size-4" />
              操作日志
            </Button>
            <Button type="button" onClick={startNew} className="cursor-pointer gap-1.5">
              <Plus className="size-4" />
              新增尺码组
            </Button>
          </div>
        </div>

        <div className="grid min-h-[560px] overflow-hidden rounded-xl border border-border bg-background shadow-sm lg:grid-cols-[minmax(230px,0.72fr)_minmax(0,1.8fr)]">
          <aside className="border-b border-border bg-muted/15 p-3 lg:border-b-0 lg:border-r">
            <div className="mb-2 flex h-8 items-center px-2 text-xs font-medium text-muted-foreground">尺码组</div>
            <div className="space-y-1">
              {isLoading ? (
                <div className="flex items-center justify-center py-14 text-sm text-muted-foreground"><Loader2 className="mr-2 size-4 animate-spin" />加载中</div>
              ) : groups.length ? groups.map((group) => {
                const selected = !isNew && group.id === selectedId
                return (
                  <button
                    key={group.id}
                    type="button"
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                      selected ? "bg-primary text-primary-foreground shadow-sm" : "hover:bg-muted",
                    )}
                    onClick={() => selectGroup(group)}
                  >
                    <Ruler className="size-4 shrink-0" />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{group.name}</span>
                    <span className={cn("shrink-0 text-xs", selected ? "text-primary-foreground/75" : "text-muted-foreground")}>{group.items.length}</span>
                  </button>
                )
              }) : (
                <div className="px-3 py-14 text-center text-sm text-muted-foreground">暂无尺码组</div>
              )}
            </div>
          </aside>

          <section className="flex min-w-0 flex-col">
            <div className="flex min-h-16 items-center justify-between gap-3 border-b border-border px-5 py-3">
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold">{isNew ? "新建尺码组" : selectedGroup?.name || "尺码组"}</h2>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {!isNew && selectedGroup ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="cursor-pointer"
                    title="删除尺码组"
                    aria-label="删除尺码组"
                    onClick={() => {
                      if (selectedGroup.product_count) {
                        setMessage({ title: "无法删除", description: `该尺码组已被 ${selectedGroup.product_count} 个商品使用，请先修改这些商品的尺码段。` })
                        return
                      }
                      setDeleteTarget(selectedGroup)
                    }}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                ) : null}
                <Button type="button" className="cursor-pointer gap-1.5" onClick={save} disabled={isSaving}>
                  {isSaving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  保存
                </Button>
              </div>
            </div>

            <div className="flex-1 p-5">
              <div className="max-w-xl space-y-1.5">
                <Label htmlFor="size-group-name">尺码组名称</Label>
                <Input id="size-group-name" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="例如：女鞋 34-39" autoComplete="off" />
              </div>

              <div className="mt-6 overflow-hidden rounded-lg border border-border">
                <table className="w-full table-fixed text-sm">
                  <thead className="bg-muted/55 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="w-16 px-3 py-2.5 font-medium">行号</th>
                      <th className="px-3 py-2.5 font-medium">尺码</th>
                      <th className="px-3 py-2.5 font-medium">条码</th>
                      <th className="w-14 px-2 py-2.5"><span className="sr-only">操作</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {draft.items.map((item, index) => (
                      <tr key={item.key} className="border-t border-border">
                        <td className="px-3 py-2 text-muted-foreground">{index + 1}</td>
                        <td className="px-3 py-1.5"><Input value={item.size_name} aria-label={`第 ${index + 1} 行尺码`} onChange={(event) => updateItem(item.key, "size_name", event.target.value)} placeholder="例如：34" autoComplete="off" /></td>
                        <td className="px-3 py-1.5"><Input value={item.barcode} aria-label={`第 ${index + 1} 行条码`} onChange={(event) => updateItem(item.key, "barcode", event.target.value)} placeholder="请输入条码" autoComplete="off" /></td>
                        <td className="px-2 py-1.5 text-center">
                          <Button type="button" variant="ghost" size="icon" className="cursor-pointer text-muted-foreground hover:text-destructive" title="删除尺码" aria-label={`删除第 ${index + 1} 行尺码`} disabled={draft.items.length === 1} onClick={() => deleteItem(item.key)}>
                            <Trash2 className="size-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Button type="button" variant="outline" className="mt-3 cursor-pointer gap-1.5" onClick={() => setDraft((current) => ({ ...current, items: [...current.items, newDraftItem()] }))}>
                <Plus className="size-4" />
                新增尺码
              </Button>
            </div>
          </section>
        </div>
      </div>

        <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除"
        description={deleteTarget?.product_count ? `尺码组 ${deleteTarget.name} 已被 ${deleteTarget.product_count} 个商品使用，不能删除。` : `确定删除尺码组 ${deleteTarget?.name || ""}？`}
        confirmLabel={isDeleting ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={removeGroup}
        onCancel={() => setDeleteTarget(null)}
        />
        <OperationLogDialog
          module="size_group"
          open={operationLogOpen}
          title="尺码组管理操作日志"
          onOpenChange={setOperationLogOpen}
        />
      <MessageDialog open={message !== null} title={message?.title || ""} description={message?.description || ""} onClose={() => setMessage(null)} />
    </div>
  )
}
