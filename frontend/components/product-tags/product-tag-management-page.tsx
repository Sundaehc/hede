"use client"

import { useEffect, useState } from "react"
import { Pencil, RefreshCw, Search, Tag } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { MessageDialog } from "@/components/confirm-dialog"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { ApiError, getProductTagMetadata, listProductTags, rebuildProductTagsFromProducts, updateProductTag } from "@/lib/api"
import type { ProductTagDefinition } from "@/lib/types"

function getError(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return "操作失败，请稍后重试"
}

export function ProductTagManagementPage() {
  const { user } = useAuth()
  const canManage = user?.role_code === "super_admin" || user?.department_code === "开发部"
  const [items, setItems] = useState<ProductTagDefinition[]>([])
  const [groups, setGroups] = useState<string[]>([])
  const [group, setGroup] = useState("all")
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [message, setMessage] = useState<string | null>(null)
  const [logsOpen, setLogsOpen] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [editingTag, setEditingTag] = useState<ProductTagDefinition | null>(null)
  const [editName, setEditName] = useState("")
  const [editGroup, setEditGroup] = useState("")
  const [editSortOrder, setEditSortOrder] = useState("0")
  const [editActive, setEditActive] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    try {
      const response = await listProductTags({ group, query })
      setItems(response.items)
    } catch (error) {
      setMessage(getError(error))
    }
  }

  useEffect(() => {
    if (!canManage) return
    void getProductTagMetadata()
      .then((response) => setGroups(response.groups))
      .catch(() => undefined)
  }, [canManage])

  useEffect(() => {
    if (!canManage) return
    void load()
  }, [canManage, group, query])

  async function rebuild() {
    if (!window.confirm("将清空现有标签和绑定，并按商品信息档案重新生成，是否继续？")) return
    setRebuilding(true)
    try {
      const response = await rebuildProductTagsFromProducts()
      setMessage(`${response.message}：${response.result.products} 个商品、${response.result.tag_definitions} 个标签、${response.result.assignments} 个绑定`)
      await load()
    } catch (error) {
      setMessage(getError(error))
    } finally {
      setRebuilding(false)
    }
  }

  function openEdit(item: ProductTagDefinition) {
    setEditingTag(item)
    setEditName(item.tag_name)
    setEditGroup(item.tag_group)
    setEditSortOrder(String(item.sort_order))
    setEditActive(item.is_active)
  }

  async function saveEdit() {
    if (!editingTag) return
    const tagName = editName.trim()
    const sortOrder = Number(editSortOrder)
    if (!tagName) {
      setMessage("标签名称不能为空")
      return
    }
    if (!Number.isInteger(sortOrder) || sortOrder < 0 || sortOrder > 9999) {
      setMessage("排序必须是 0 到 9999 的整数")
      return
    }
    setSaving(true)
    try {
      const response = await updateProductTag(editingTag.id, {
        tag_name: tagName,
        tag_group: editGroup,
        sort_order: sortOrder,
        is_active: editActive,
      })
      setMessage(response.message)
      setEditingTag(null)
      await load()
    } catch (error) {
      setMessage(getError(error))
    } finally {
      setSaving(false)
    }
  }

  if (!canManage) {
    return (
      <div className="app-page">
        <div className="app-content">
          <section className="surface-panel p-12 text-center">
            <h1 className="page-title">无权访问商品标签</h1>
            <p className="mt-2 text-sm text-muted-foreground">商品标签管理仅限开发部和超级管理员使用。</p>
          </section>
        </div>
      </div>
    )
  }

  return (
    <div className="app-page">
      <div className="app-content space-y-5">
        <div className="page-header">
          <div>
            <h1 className="page-title">商品标签管理</h1>
            <p className="page-subtitle">标签默认根据商品信息档案字段生成，支持人工调整并在重建时保留。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" className="cursor-pointer" disabled={rebuilding} onClick={() => void rebuild()}>
              <RefreshCw className={`mr-1 size-4 ${rebuilding ? "animate-spin" : ""}`} />
              从商品档案重建
            </Button>
            <Button type="button" variant="outline" className="cursor-pointer" onClick={() => setLogsOpen(true)}>
              操作日志
            </Button>
          </div>
        </div>

        <section className="surface-panel overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-border p-4">
            <div className="relative min-w-60 flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
              <Input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setQuery(queryInput.trim())
                }}
                placeholder="搜索标签名称"
                className="pl-9"
              />
            </div>
            <Select value={group} onChange={(event) => setGroup(event.target.value)} className="w-36">
              <option value="all">全部分组</option>
              {groups.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
            <Button type="button" variant="outline" className="cursor-pointer" onClick={() => setQuery(queryInput.trim())}>搜索</Button>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <article key={item.id} className="rounded-xl border border-border/70 bg-card p-4 shadow-xs">
                <div className="flex items-start gap-3">
                  <Tag className="mt-0.5 size-4 text-primary" />
                  <div className="min-w-0 flex-1">
                    <h2 className="font-semibold">{item.tag_name}</h2>
                    <p className="mt-1 text-xs text-muted-foreground">{item.tag_group}</p>
                    <p className="mt-3 text-xs text-muted-foreground">
                      {item.is_manual_override ? "人工修改" : "商品档案规则生成"}
                    </p>
                  </div>
                  <Button type="button" variant="ghost" size="icon" className="shrink-0 cursor-pointer" onClick={() => openEdit(item)} aria-label={`编辑${item.tag_name}`}>
                    <Pencil className="size-4" />
                  </Button>
                </div>
              </article>
            ))}
          </div>
          {items.length === 0 ? <div className="p-12 text-center text-sm text-muted-foreground">暂无标签</div> : null}
        </section>
      </div>
      <Dialog open={editingTag !== null} onOpenChange={(open) => { if (!open && !saving) setEditingTag(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑商品标签</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="product-tag-name">标签名称 *</Label>
              <Input id="product-tag-name" value={editName} onChange={(event) => setEditName(event.target.value)} disabled={saving} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="product-tag-group">标签分组 *</Label>
              <Select id="product-tag-group" value={editGroup} onChange={(event) => setEditGroup(event.target.value)} disabled={saving}>
                {groups.map((item) => <option key={item} value={item}>{item}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="product-tag-sort-order">排序</Label>
              <Input id="product-tag-sort-order" type="number" min={0} max={9999} value={editSortOrder} onChange={(event) => setEditSortOrder(event.target.value)} disabled={saving} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={editActive} onChange={(event) => setEditActive(event.target.checked)} disabled={saving} />
              启用标签
            </label>
            <p className="text-xs text-muted-foreground">保存后会标记为人工修改；之后重建标签时会保留本次修改。</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" className="cursor-pointer" onClick={() => setEditingTag(null)} disabled={saving}>取消</Button>
            <Button type="button" className="cursor-pointer" onClick={() => void saveEdit()} disabled={saving}>{saving ? "保存中..." : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <OperationLogDialog module="product_tag" open={logsOpen} title="商品标签操作日志" onOpenChange={setLogsOpen} />
      <MessageDialog open={message !== null} title="商品标签" description={message || ""} onClose={() => setMessage(null)} />
    </div>
  )
}
