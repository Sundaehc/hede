"use client"

import { useCallback, useEffect, useState } from "react"
import { Edit, History, Plus, RefreshCw, Trash2 } from "lucide-react"
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
import { ConfirmDialog, MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import {
  ApiError,
  createInventoryAccountSubject,
  deleteInventoryAccountSubject,
  listInventoryAccountSubjects,
  updateInventoryAccountSubject,
  type InventoryAccountSubject,
} from "@/lib/api"

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError)
    return error.message || `请求失败（${error.status}）`
  if (error instanceof Error) return error.message
  return "发生未知错误"
}

export default function AccountSubjectsPage() {
  const [items, setItems] = useState<InventoryAccountSubject[]>([])
  const [name, setName] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [editTarget, setEditTarget] = useState<InventoryAccountSubject | null>(
    null
  )
  const [editName, setEditName] = useState("")
  const [renameConfirmOpen, setRenameConfirmOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] =
    useState<InventoryAccountSubject | null>(null)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [messageOpen, setMessageOpen] = useState(false)
  const [messageContent, setMessageContent] = useState({
    title: "",
    description: "",
  })

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

  const openEdit = (item: InventoryAccountSubject) => {
    setEditTarget(item)
    setEditName(item.name)
  }

  const saveUpdate = async () => {
    if (!editTarget) return
    const nextName = editName.trim()
    setIsSaving(true)
    try {
      const response = await updateInventoryAccountSubject(editTarget.id, {
        name: nextName,
      })
      setRenameConfirmOpen(false)
      setEditTarget(null)
      await load()
      showMessage("保存成功", response.message)
    } catch (error) {
      showMessage("保存失败", getErrorMessage(error))
    } finally {
      setIsSaving(false)
    }
  }

  const handleUpdate = () => {
    if (!editTarget) return
    const nextName = editName.trim()
    if (!nextName) {
      showMessage("保存失败", "科目名称不能为空")
      return
    }
    if (nextName === editTarget.name.trim()) {
      setEditTarget(null)
      return
    }
    setRenameConfirmOpen(true)
  }

  return (
    <div className="app-page">
      <div className="app-content-narrow">
        <div className="page-header">
          <div>
            <h1 className="page-title">科目管理</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setOperationLogOpen(true)}
              className="cursor-pointer"
            >
              <History className="h-4 w-4" />
              <span className="ml-1.5">操作日志</span>
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void load()}
              disabled={isLoading}
              className="cursor-pointer"
            >
              <RefreshCw
                className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
              />
              <span className="ml-1.5">刷新</span>
            </Button>
          </div>
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
            <Button
              onClick={handleCreate}
              disabled={isSaving}
              className="cursor-pointer"
            >
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
                <th className="w-36 px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td
                    colSpan={2}
                    className="px-4 py-12 text-center text-muted-foreground"
                  >
                    加载中...
                  </td>
                </tr>
              )}
              {!isLoading && items.length === 0 && (
                <tr>
                  <td
                    colSpan={2}
                    className="px-4 py-12 text-center text-muted-foreground"
                  >
                    暂无科目
                  </td>
                </tr>
              )}
              {!isLoading &&
                items.map((item) => (
                  <tr key={item.id} className="table-row">
                    <td className="px-4 py-2.5 font-medium">{item.name}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openEdit(item)}
                          disabled={isSaving}
                          className="cursor-pointer"
                          aria-label={`编辑科目 ${item.name}`}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
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
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog
        open={editTarget !== null}
        onOpenChange={(open) => {
          if (!open && !isSaving) setEditTarget(null)
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑科目</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <Label htmlFor="edit-subject-name">科目名称</Label>
            <Input
              id="edit-subject-name"
              value={editName}
              onChange={(event) => setEditName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault()
                  handleUpdate()
                }
              }}
              className="mt-1.5"
              placeholder="请输入科目名称"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditTarget(null)}
              disabled={isSaving}
              className="cursor-pointer"
            >
              取消
            </Button>
            <Button
              onClick={handleUpdate}
              disabled={isSaving}
              className="cursor-pointer"
            >
              {isSaving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={renameConfirmOpen}
        title="确认修改科目名称"
        description={`将科目“${editTarget?.name || ""}”修改为“${editName.trim()}”，会同步更新对应的历史经营历程明细，请确定是否修改。`}
        confirmLabel={isSaving ? "修改中..." : "确认修改"}
        onConfirm={() => void saveUpdate()}
        onCancel={() => setRenameConfirmOpen(false)}
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

      <MessageDialog
        open={messageOpen}
        title={messageContent.title}
        description={messageContent.description}
        onClose={() => setMessageOpen(false)}
      />

      <OperationLogDialog
        module="account_subject"
        title="科目管理操作日志"
        open={operationLogOpen}
        onOpenChange={setOperationLogOpen}
      />
    </div>
  )
}
