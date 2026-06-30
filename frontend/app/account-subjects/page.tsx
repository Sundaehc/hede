"use client"

import { useCallback, useEffect, useState } from "react"
import { Plus, RefreshCw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import {
  ApiError,
  createInventoryAccountSubject,
  deleteInventoryAccountSubject,
  listInventoryAccountSubjects,
  type InventoryAccountSubject,
} from "@/lib/api"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function AccountSubjectsPage() {
  const [items, setItems] = useState<InventoryAccountSubject[]>([])
  const [name, setName] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<InventoryAccountSubject | null>(null)
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
    void load()
  }, [load])

  const handleCreate = async () => {
    const nextName = name.trim()
    if (!nextName) {
      showMessage("新增失败", "科目名称不能为空")
      return
    }
    setIsSaving(true)
    try {
      await createInventoryAccountSubject({ code: "", name: nextName })
      setName("")
      await load()
    } catch (error) {
      showMessage("新增失败", getErrorMessage(error))
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

  return (
    <div className="app-page">
      <div className="app-content-narrow">
        <div className="page-header">
          <div>
            <h1 className="page-title">科目管理</h1>
          </div>
          <Button size="sm" variant="outline" onClick={() => void load()} disabled={isLoading} className="cursor-pointer">
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            <span className="ml-1.5">刷新</span>
          </Button>
        </div>

        <div className="surface-panel mb-4 p-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <div className="space-y-1.5">
              <Label htmlFor="subject-name">新增科目</Label>
              <Input
                id="subject-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault()
                    void handleCreate()
                  }
                }}
                placeholder="例如：罚款收入、付货款"
              />
            </div>
            <Button onClick={handleCreate} disabled={isSaving} className="cursor-pointer">
              <Plus className="h-4 w-4" />
              <span className="ml-1.5">新增</span>
            </Button>
          </div>
        </div>

        <div className="table-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="table-head-row">
                <th className="px-4 py-3 font-medium">科目名称</th>
                <th className="w-28 px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">加载中...</td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td colSpan={2} className="px-4 py-12 text-center text-muted-foreground">暂无科目</td>
                </tr>
              )}
              {!isLoading && items.map((item) => (
                <tr key={item.id} className="table-row">
                  <td className="px-4 py-2.5 font-medium">{item.name}</td>
                  <td className="px-4 py-2.5 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleteTarget(item)}
                      disabled={isSaving}
                      className="cursor-pointer"
                      aria-label={`删除科目 ${item.name}`}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除科目"
        description={`确定删除科目 ${deleteTarget?.name || ""}？已保存的单据明细不会被改动。`}
        confirmLabel={isSaving ? "删除中..." : "删除"}
        variant="destructive"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <MessageDialog
        open={messageOpen}
        title={messageContent.title}
        description={messageContent.description}
        onClose={() => setMessageOpen(false)}
      />
    </div>
  )
}
