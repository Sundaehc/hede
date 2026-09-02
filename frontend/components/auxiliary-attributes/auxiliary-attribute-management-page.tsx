"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  Download,
  History,
  ListFilter,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
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
import { Select } from "@/components/ui/select"
import {
  ApiError,
  createProductAuxiliaryAttribute,
  deleteProductAuxiliaryAttribute,
  exportProductAuxiliaryAttributes,
  getProductAuxiliaryAttributeMetadata,
  listManagedProductAuxiliaryAttributes,
  updateProductAuxiliaryAttribute,
} from "@/lib/api"
import type {
  ManagedProductAuxiliaryAttributeItem,
  ProductAuxiliaryAttributeScope,
  ProductAuxiliaryAttributeType,
  ProductAuxiliaryAttributeWritePayload,
} from "@/lib/types"
import { cn } from "@/lib/utils"


const PAGE_SIZE = 50
const EMPTY_DRAFT: ProductAuxiliaryAttributeWritePayload = {
  brand_scope: "",
  attribute_type: "",
  attribute_name: "",
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return "操作失败，请稍后重试"
}

function formatDateTime(value: string | null) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date)
}

export function AuxiliaryAttributeManagementPage() {
  const { user } = useAuth()
  const canManage =
    user?.role_code === "super_admin" ||
    ["商品部", "开发部"].includes(user?.department_code ?? "")
  const [scopes, setScopes] = useState<ProductAuxiliaryAttributeScope[]>([])
  const [attributeTypes, setAttributeTypes] = useState<
    ProductAuxiliaryAttributeType[]
  >([])
  const [selectedScope, setSelectedScope] = useState("")
  const [selectedType, setSelectedType] = useState("all")
  const [items, setItems] = useState<ManagedProductAuxiliaryAttributeItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [queryInput, setQueryInput] = useState("")
  const [query, setQuery] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingItem, setEditingItem] =
    useState<ManagedProductAuxiliaryAttributeItem | null>(null)
  const [draft, setDraft] =
    useState<ProductAuxiliaryAttributeWritePayload>(EMPTY_DRAFT)
  const [isSaving, setIsSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] =
    useState<ManagedProductAuxiliaryAttributeItem | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [message, setMessage] = useState<{
    title: string
    description: string
  } | null>(null)
  const loadRequestIdRef = useRef(0)

  const selectedScopeItem = useMemo(
    () => scopes.find((scope) => scope.value === selectedScope) ?? null,
    [scopes, selectedScope]
  )
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadMetadata = useCallback(async () => {
    try {
      const response = await getProductAuxiliaryAttributeMetadata()
      setScopes(response.scopes)
      setAttributeTypes(response.attribute_types)
      setSelectedScope((current) =>
        response.scopes.some((scope) => scope.value === current)
          ? current
          : response.scopes[0]?.value || ""
      )
    } catch (error) {
      setScopes([])
      setAttributeTypes([])
      setMessage({ title: "加载失败", description: getErrorMessage(error) })
    }
  }, [])

  const loadItems = useCallback(async () => {
    await Promise.resolve()
    const requestId = ++loadRequestIdRef.current
    if (!selectedScope) {
      setItems([])
      setTotal(0)
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    try {
      const response = await listManagedProductAuxiliaryAttributes({
        brandScope: selectedScope,
        attributeType: selectedType,
        query,
        page,
        pageSize: PAGE_SIZE,
      })
      if (requestId !== loadRequestIdRef.current) return
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE))
      if (response.total > 0 && page > lastPage) {
        setPage(lastPage)
        return
      }
      setItems(response.items)
      setTotal(response.total)
    } catch (error) {
      if (requestId !== loadRequestIdRef.current) return
      setItems([])
      setTotal(0)
      setMessage({ title: "加载失败", description: getErrorMessage(error) })
    } finally {
      if (requestId === loadRequestIdRef.current) setIsLoading(false)
    }
  }, [page, query, selectedScope, selectedType])

  useEffect(() => {
    if (canManage) void Promise.resolve().then(loadMetadata)
  }, [canManage, loadMetadata])

  useEffect(() => {
    if (canManage) void Promise.resolve().then(loadItems)
  }, [canManage, loadItems])

  const selectScope = (scope: string) => {
    if (scope === selectedScope) return
    setSelectedScope(scope)
    setTotal(scopes.find((item) => item.value === scope)?.total ?? 0)
    setPage(1)
  }

  const openCreate = () => {
    setEditingItem(null)
    setDraft({
      brand_scope: selectedScope || scopes[0]?.value || "",
      attribute_type:
        selectedType !== "all"
          ? selectedType
          : attributeTypes[0]?.value || "",
      attribute_name: "",
    })
    setEditorOpen(true)
  }

  const openEdit = (item: ManagedProductAuxiliaryAttributeItem) => {
    setEditingItem(item)
    setDraft({
      brand_scope: item.brand_scope,
      attribute_type: item.attribute_type,
      attribute_name: item.attribute_name,
    })
    setEditorOpen(true)
  }

  const save = async () => {
    const payload = {
      brand_scope: draft.brand_scope.trim(),
      attribute_type: draft.attribute_type.trim(),
      attribute_name: draft.attribute_name.trim(),
    }
    if (
      !payload.brand_scope ||
      !payload.attribute_type ||
      !payload.attribute_name
    ) {
      setMessage({
        title: "保存失败",
        description: "请填写适用品牌、属性类型和属性值",
      })
      return
    }
    setIsSaving(true)
    try {
      const result = editingItem
        ? await updateProductAuxiliaryAttribute(editingItem.id, payload)
        : await createProductAuxiliaryAttribute(payload)
      setEditorOpen(false)
      await Promise.all([loadMetadata(), loadItems()])
      setMessage({
        title: editingItem ? "保存成功" : "新增成功",
        description: result.message,
      })
    } catch (error) {
      setMessage({ title: "保存失败", description: getErrorMessage(error) })
    } finally {
      setIsSaving(false)
    }
  }

  const remove = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      const result = await deleteProductAuxiliaryAttribute(deleteTarget.id)
      setDeleteTarget(null)
      await Promise.all([loadMetadata(), loadItems()])
      setMessage({ title: "删除成功", description: result.message })
    } catch (error) {
      setMessage({ title: "删除失败", description: getErrorMessage(error) })
    } finally {
      setIsDeleting(false)
    }
  }

  const exportAttributes = async () => {
    if (!selectedScope) return
    setIsExporting(true)
    try {
      const blob = await exportProductAuxiliaryAttributes({
        brandScope: selectedScope,
        attributeType: selectedType,
        query,
      })
      const typeLabel = selectedType === "all" ? "全部类型" : selectedType
      const link = document.createElement("a")
      link.href = URL.createObjectURL(blob)
      link.download = `辅助属性管理_${selectedScopeItem?.label || selectedScope}_${typeLabel}.xlsx`
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (error) {
      setMessage({ title: "导出失败", description: getErrorMessage(error) })
    } finally {
      setIsExporting(false)
    }
  }

  if (!canManage) {
    return (
      <div className="app-page">
        <div className="app-content py-12 text-sm text-muted-foreground">
          暂无访问权限
        </div>
      </div>
    )
  }

  return (
    <div className="app-page">
      <div className="app-content space-y-4">
        <div className="page-header">
          <h1 className="page-title">辅助属性管理</h1>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              className="cursor-pointer gap-1.5 text-xs"
              onClick={() => void exportAttributes()}
              disabled={!selectedScope || isExporting}
            >
              {isExporting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Download className="size-4" />
              )}
              {isExporting ? "导出中" : "导出"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="cursor-pointer gap-1.5 text-xs"
              onClick={() => setOperationLogOpen(true)}
            >
              <History className="size-4" />
              操作日志
            </Button>
            <Button
              type="button"
              className="cursor-pointer gap-1.5 text-xs"
              onClick={openCreate}
              disabled={!selectedScope || attributeTypes.length === 0}
            >
              <Plus className="size-4" />
              新增属性
            </Button>
          </div>
        </div>

        <div className="flex min-h-11 flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-1.5 shadow-xs">
          {scopes.map((scope) => (
            <button
              key={scope.value}
              type="button"
              onClick={() => selectScope(scope.value)}
              className={cn(
                "flex h-8 cursor-pointer items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors",
                selectedScope === scope.value
                  ? "bg-foreground text-background shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <span>{scope.label}</span>
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[11px] tabular-nums",
                  selectedScope === scope.value
                    ? "bg-background/15"
                    : "bg-muted"
                )}
              >
                {scope.total}
              </span>
            </button>
          ))}
        </div>

        <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border p-4">
            <form
              className="flex w-full flex-wrap items-center gap-2 lg:max-w-3xl"
              onSubmit={(event) => {
                event.preventDefault()
                setPage(1)
                setQuery(queryInput.trim())
              }}
            >
              <Select
                aria-label="属性类型筛选"
                value={selectedType}
                onChange={(event) => {
                  setSelectedType(event.target.value)
                  setPage(1)
                }}
                className="w-40 cursor-pointer"
              >
                <option value="all">全部属性类型</option>
                {attributeTypes.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.value}
                  </option>
                ))}
              </Select>
              <div className="relative min-w-56 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  placeholder="搜索属性类型或属性值"
                  className="pl-9"
                />
              </div>
              <Button type="submit" className="cursor-pointer">
                搜索
              </Button>
            </form>
            <div className="text-sm text-muted-foreground">
              {selectedScopeItem?.label || "适用品牌"} · 共 {total} 条
            </div>
          </div>

          <div className="relative h-[clamp(420px,64svh,680px)] overflow-auto">
            {isLoading && items.length > 0 ? (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-card/70 backdrop-blur-[1px]">
                <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground shadow-sm">
                  <Loader2 className="size-4 animate-spin" />
                  加载中
                </div>
              </div>
            ) : null}
            <table className="w-full min-w-[760px] table-fixed text-sm">
              <thead className="sticky top-0 z-10 bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-20 px-4 py-3 font-medium">序号</th>
                  <th className="w-44 px-4 py-3 font-medium">属性类型</th>
                  <th className="px-4 py-3 font-medium">属性值</th>
                  <th className="w-44 px-4 py-3 font-medium">最后修改时间</th>
                  <th className="sticky right-0 w-28 bg-muted px-4 py-3 text-right font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading && items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="h-64 text-center text-muted-foreground"
                    >
                      <Loader2 className="mr-2 inline size-4 animate-spin" />
                      加载中
                    </td>
                  </tr>
                ) : items.length ? (
                  items.map((item, index) => (
                    <tr
                      key={item.id}
                      className="group border-t border-border hover:bg-muted/25"
                    >
                      <td className="px-4 py-3 text-muted-foreground tabular-nums">
                        {(page - 1) * PAGE_SIZE + index + 1}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-md bg-muted px-2 py-1 text-xs font-medium">
                          {item.attribute_type}
                        </span>
                      </td>
                      <td className="break-words px-4 py-3 font-medium text-foreground">
                        {item.attribute_name}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {formatDateTime(item.updated_at || item.created_at)}
                      </td>
                      <td className="sticky right-0 bg-card px-3 py-2.5 group-hover:bg-muted/25">
                        <div className="flex justify-end gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="cursor-pointer"
                            title="编辑辅助属性"
                            aria-label={`编辑 ${item.attribute_name}`}
                            onClick={() => openEdit(item)}
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="cursor-pointer text-muted-foreground hover:text-destructive"
                            title="删除辅助属性"
                            aria-label={`删除 ${item.attribute_name}`}
                            onClick={() => setDeleteTarget(item)}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={5}
                      className="h-64 text-center text-sm text-muted-foreground"
                    >
                      <ListFilter className="mx-auto mb-3 size-7 opacity-45" />
                      暂无辅助属性
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex min-h-14 items-center justify-between gap-3 border-t border-border px-4 py-2">
            <span className="text-xs text-muted-foreground">
              第 {total ? (page - 1) * PAGE_SIZE + 1 : 0}-
              {Math.min(page * PAGE_SIZE, total)} 条
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="cursor-pointer"
                disabled={page <= 1 || isLoading}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                aria-label="上一页"
              >
                <ChevronLeft className="size-4" />
              </Button>
              <span className="min-w-20 text-center text-xs tabular-nums text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="cursor-pointer"
                disabled={page >= totalPages || isLoading}
                onClick={() =>
                  setPage((current) => Math.min(totalPages, current + 1))
                }
                aria-label="下一页"
              >
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
        </section>
      </div>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingItem ? "编辑辅助属性" : "新增辅助属性"}
            </DialogTitle>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              void save()
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="auxiliary-scope">适用品牌</Label>
              <Select
                id="auxiliary-scope"
                value={draft.brand_scope}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    brand_scope: event.target.value,
                  }))
                }
                className="cursor-pointer"
              >
                {scopes.map((scope) => (
                  <option key={scope.value} value={scope.value}>
                    {scope.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="auxiliary-type">属性类型</Label>
              <Select
                id="auxiliary-type"
                value={draft.attribute_type}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    attribute_type: event.target.value,
                  }))
                }
                className="cursor-pointer"
              >
                {attributeTypes.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.value}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="auxiliary-name">属性值</Label>
              <Input
                id="auxiliary-name"
                value={draft.attribute_name}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    attribute_name: event.target.value,
                  }))
                }
                placeholder="请输入属性值"
                autoComplete="off"
              />
            </div>
            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                className="cursor-pointer"
                onClick={() => setEditorOpen(false)}
              >
                取消
              </Button>
              <Button
                type="submit"
                className="cursor-pointer"
                disabled={isSaving}
              >
                {isSaving ? <Loader2 className="size-4 animate-spin" /> : null}
                {isSaving ? "保存中" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除辅助属性"
        description={`确定删除“${deleteTarget?.brand_scope_label || ""} / ${deleteTarget?.attribute_type || ""} / ${deleteTarget?.attribute_name || ""}”？删除后，该选项将不再出现在商品档案的下拉列表中。`}
        confirmLabel={isDeleting ? "删除中" : "删除"}
        variant="destructive"
        onConfirm={() => void remove()}
        onCancel={() => setDeleteTarget(null)}
      />
      <OperationLogDialog
        module="product_auxiliary_attribute"
        open={operationLogOpen}
        title="辅助属性管理操作日志"
        onOpenChange={setOperationLogOpen}
      />
      <MessageDialog
        open={message !== null}
        title={message?.title || ""}
        description={message?.description || ""}
        onClose={() => setMessage(null)}
      />
    </div>
  )
}
