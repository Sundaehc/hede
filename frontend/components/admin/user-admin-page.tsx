"use client"

import { useEffect, useMemo, useState, type ReactNode } from "react"
import { AlertCircle, Ban, Building2, CheckCircle2, History, Loader2, RefreshCw, Save, ShieldCheck, UserCog, Users, type LucideIcon } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getAuthOptions, listAdminUsers, updateAdminUser } from "@/lib/api"
import type { AuthDepartment, AuthRole, AuthUser } from "@/lib/types"
import { cn } from "@/lib/utils"


type UserDraft = {
  display_name: string
  department_code: string
  role_code: string
  status: string
  password: string
}


const STATUS_OPTIONS = [
  { value: "active", label: "启用" },
  { value: "disabled", label: "禁用" },
]

const STATUS_META = {
  active: {
    label: "启用",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dotClassName: "bg-emerald-500",
  },
  disabled: {
    label: "禁用",
    className: "border-rose-200 bg-rose-50 text-rose-700",
    dotClassName: "bg-rose-500",
  },
} as const


function draftFromUser(user: AuthUser): UserDraft {
  return {
    display_name: user.display_name,
    department_code: user.department_code,
    role_code: user.role_code,
    status: user.status,
    password: "",
  }
}

function userInitial(user: AuthUser) {
  return (user.display_name || user.username || "?").trim().slice(0, 1).toUpperCase()
}

function getStatusMeta(status: string) {
  return STATUS_META[status as keyof typeof STATUS_META] ?? STATUS_META.disabled
}

function hasDraftChanges(user: AuthUser, draft: UserDraft) {
  return (
    draft.display_name !== user.display_name
    || draft.department_code !== user.department_code
    || draft.role_code !== user.role_code
    || draft.status !== user.status
    || draft.password.length > 0
  )
}

function statusLabel(status: string) {
  return STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status
}

function UserIdentity({ user }: { user: AuthUser }) {
  const meta = getStatusMeta(user.status)
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-sm font-semibold text-foreground">
        {userInitial(user)}
      </div>
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate font-semibold text-foreground">{user.username}</p>
          <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", meta.className)}>
            <span className={cn("h-1.5 w-1.5 rounded-full", meta.dotClassName)} />
            {meta.label}
          </span>
        </div>
      </div>
    </div>
  )
}

function StatTile({ icon: Icon, label, value, tone = "neutral" }: {
  icon: LucideIcon
  label: string
  value: string | number
  tone?: "neutral" | "good" | "warn"
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3 shadow-xs">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <span className={cn(
          "flex h-7 w-7 items-center justify-center rounded-lg",
          tone === "good" && "bg-emerald-50 text-emerald-700",
          tone === "warn" && "bg-rose-50 text-rose-700",
          tone === "neutral" && "bg-muted text-muted-foreground",
        )}>
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-normal text-foreground">{value}</p>
    </div>
  )
}

function FieldLabel({ children }: { children: ReactNode }) {
  return <p className="mb-1.5 text-xs font-medium text-muted-foreground">{children}</p>
}


export function UserAdminPage() {
  const { hasPermission } = useAuth()
  const [users, setUsers] = useState<AuthUser[]>([])
  const [departments, setDepartments] = useState<AuthDepartment[]>([])
  const [roles, setRoles] = useState<AuthRole[]>([])
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({})
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [message, setMessage] = useState("")
  const [operationLogOpen, setOperationLogOpen] = useState(false)

  const rolesByDepartment = useMemo(() => {
    return roles.reduce<Record<string, AuthRole[]>>((acc, role) => {
      const key = role.department_code ?? "all"
      acc[key] = [...(acc[key] ?? []), role]
      return acc
    }, {})
  }, [roles])

  const userStats = useMemo(() => {
    const active = users.filter((user) => user.status === "active").length
    const disabled = users.filter((user) => user.status === "disabled").length
    const departmentCount = new Set(users.map((user) => user.department_code).filter(Boolean)).size
    return { active, disabled, departmentCount }
  }, [users])

  const roleByCode = useMemo(() => {
    return Object.fromEntries(roles.map((role) => [role.code, role]))
  }, [roles])

  const load = async () => {
    setLoading(true)
    setMessage("")
    try {
      const [options, userResponse] = await Promise.all([getAuthOptions(), listAdminUsers()])
      setDepartments(options.departments)
      setRoles(options.roles)
      setUsers(userResponse.items)
      setDrafts(Object.fromEntries(userResponse.items.map((user) => [user.id, draftFromUser(user)])))
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "加载用户失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (hasPermission("system.admin")) {
      void load()
    } else {
      setLoading(false)
    }
  }, [hasPermission])

  const updateDraft = (userId: number, patch: Partial<UserDraft>) => {
    setDrafts((current) => ({
      ...current,
      [userId]: { ...current[userId], ...patch },
    }))
  }

  const saveUser = async (user: AuthUser) => {
    const draft = drafts[user.id]
    if (!draft) return
    setSavingId(user.id)
    setMessage("")
    try {
      const response = await updateAdminUser(user.id, {
        display_name: draft.display_name,
        department_code: draft.department_code,
        role_code: draft.role_code,
        status: draft.status,
        ...(draft.password ? { password: draft.password } : {}),
      })
      setUsers((current) => current.map((item) => item.id === user.id ? response.item : item))
      setDrafts((current) => ({ ...current, [user.id]: draftFromUser(response.item) }))
      setMessage("用户已更新")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSavingId(null)
    }
  }

  const renderUserForm = (user: AuthUser, layout: "table" | "card") => {
    const draft = drafts[user.id] ?? draftFromUser(user)
    const availableRoles = [
      ...(rolesByDepartment.all ?? []),
      ...(rolesByDepartment[draft.department_code] ?? []),
    ]
    const selectedRole = availableRoles.find((role) => role.code === draft.role_code) ?? roleByCode[draft.role_code]
    const changed = hasDraftChanges(user, draft)
    const isSaving = savingId === user.id
    const saveButton = (
      <Button
        type="button"
        size="sm"
        variant={changed ? "default" : "outline"}
        onClick={() => void saveUser(user)}
        disabled={!changed || isSaving}
        className="min-w-20"
      >
        {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        {isSaving ? "保存中" : "保存"}
      </Button>
    )
    const changeDepartment = (departmentCode: string) => {
      const nextRoles = [
        ...(rolesByDepartment.all ?? []),
        ...(rolesByDepartment[departmentCode] ?? []),
      ]
      updateDraft(user.id, {
        department_code: departmentCode,
        role_code: nextRoles.some((role) => role.code === draft.role_code) ? draft.role_code : nextRoles[0]?.code ?? draft.role_code,
      })
    }

    if (layout === "table") {
      return (
        <>
          <td className="px-3 py-3 align-top">
            <Input
              value={draft.display_name}
              onChange={(event) => updateDraft(user.id, { display_name: event.target.value })}
              className="h-9 bg-background"
            />
          </td>
          <td className="px-3 py-3 align-top">
            <Select
              value={draft.department_code}
              onChange={(event) => changeDepartment(event.target.value)}
              className="h-9 bg-background"
            >
              {departments.map((department) => (
                <option key={department.code} value={department.code}>{department.name}</option>
              ))}
            </Select>
          </td>
          <td className="px-3 py-3 align-top">
            <Select
              value={draft.role_code}
              onChange={(event) => updateDraft(user.id, { role_code: event.target.value })}
              className="h-9 bg-background"
            >
              {availableRoles.map((role) => (
                <option key={role.code} value={role.code}>{role.name}</option>
              ))}
            </Select>
            <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-muted-foreground">
              {selectedRole?.description || "暂无角色说明"}
            </p>
          </td>
          <td className="px-3 py-3 align-top">
            <Select
              value={draft.status}
              onChange={(event) => updateDraft(user.id, { status: event.target.value })}
              className="h-9 bg-background"
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status.value} value={status.value}>{status.label}</option>
              ))}
            </Select>
          </td>
          <td className="px-3 py-3 align-top">
            <Input
              type="password"
              value={draft.password}
              placeholder="留空不修改"
              onChange={(event) => updateDraft(user.id, { password: event.target.value })}
              className="h-9 bg-background"
            />
          </td>
          <td className="px-3 py-3 text-right align-top">
            <div className="flex flex-col items-end gap-1.5">
              {saveButton}
              <span className={cn("text-[11px]", changed ? "text-primary" : "text-muted-foreground")}>
                {changed ? "未保存" : "已同步"}
              </span>
            </div>
          </td>
        </>
      )
    }

    return (
      <>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <FieldLabel>姓名</FieldLabel>
            <Input
              value={draft.display_name}
              onChange={(event) => updateDraft(user.id, { display_name: event.target.value })}
              className="h-9 bg-background"
            />
          </div>
          <div>
            <FieldLabel>部门</FieldLabel>
            <Select
              value={draft.department_code}
              onChange={(event) => changeDepartment(event.target.value)}
              className="h-9 bg-background"
            >
              {departments.map((department) => (
                <option key={department.code} value={department.code}>{department.name}</option>
              ))}
            </Select>
          </div>
          <div className="sm:col-span-2">
            <FieldLabel>角色</FieldLabel>
            <Select
              value={draft.role_code}
              onChange={(event) => updateDraft(user.id, { role_code: event.target.value })}
              className="h-9 bg-background"
            >
              {availableRoles.map((role) => (
                <option key={role.code} value={role.code}>{role.name}</option>
              ))}
            </Select>
            <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-muted-foreground">
              {selectedRole?.description || "暂无角色说明"}
            </p>
          </div>
          <div>
            <FieldLabel>状态</FieldLabel>
            <Select
              value={draft.status}
              onChange={(event) => updateDraft(user.id, { status: event.target.value })}
              className="h-9 bg-background"
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status.value} value={status.value}>{status.label}</option>
              ))}
            </Select>
          </div>
          <div>
            <FieldLabel>新密码</FieldLabel>
            <Input
              type="password"
              value={draft.password}
              placeholder="留空不修改"
              onChange={(event) => updateDraft(user.id, { password: event.target.value })}
              className="h-9 bg-background"
            />
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
          <span className={cn("text-xs", changed ? "text-primary" : "text-muted-foreground")}>
            {changed ? "有未保存修改" : "暂无修改"}
          </span>
          {saveButton}
        </div>
      </>
    )
  }

  if (!hasPermission("system.admin")) {
    return (
      <div className="app-page">
        <div className="app-content">
          <div className="surface-panel p-8 text-sm text-muted-foreground">权限不足，只有超级管理员可以访问用户管理。</div>
        </div>
      </div>
    )
  }

  return (
    <div className="app-page">
      <div className="app-content min-w-[760px]">
        <div className="page-header">
          <div>
            <h1 className="page-title">用户管理</h1>
            <p className="page-subtitle">管理登录账号、部门、角色和账号状态</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={() => setOperationLogOpen(true)}>
              <History className="h-3.5 w-3.5" />
              操作日志
            </Button>
            <Button type="button" variant="outline" onClick={() => void load()} disabled={loading}>
              <RefreshCw className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              刷新
            </Button>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile icon={Users} label="账号总数" value={users.length} />
          <StatTile icon={CheckCircle2} label="启用账号" value={userStats.active} tone="good" />
          <StatTile icon={Ban} label="禁用账号" value={userStats.disabled} tone="warn" />
          <StatTile icon={Building2} label="涉及部门" value={userStats.departmentCount} />
        </div>

        {message ? (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
            <AlertCircle className="h-4 w-4 shrink-0 text-primary" />
            <span>{message}</span>
          </div>
        ) : null}

        <div className="surface-panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  系统账号
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">禁用账号会立即失去登录权限</p>
              </div>
            </div>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-3 py-1 text-xs text-muted-foreground">
              <UserCog className="h-3.5 w-3.5" />
              {loading ? "正在加载" : `${users.length} 个账号`}
            </div>
          </div>

          <div className="hidden overflow-x-auto xl:block">
            <table className="w-full min-w-[990px] text-sm">
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th className="w-[220px] px-3 py-3 text-left font-medium">账号</th>
                  <th className="w-[140px] px-3 py-3 text-left font-medium">姓名</th>
                  <th className="w-[110px] px-3 py-3 text-left font-medium">部门</th>
                  <th className="w-[210px] px-3 py-3 text-left font-medium">角色</th>
                  <th className="w-[90px] px-3 py-3 text-left font-medium">状态</th>
                  <th className="w-[130px] px-3 py-3 text-left font-medium">新密码</th>
                  <th className="w-[90px] px-3 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {loading && users.length === 0 ? (
                  <tr>
                    <td className="px-4 py-12 text-center text-muted-foreground" colSpan={7}>
                      正在加载用户...
                    </td>
                  </tr>
                ) : null}
                {users.map((user) => {
                  return (
                    <tr key={user.id} className="bg-card/40 transition-colors hover:bg-muted/30">
                      <td className="px-3 py-3 align-top">
                        <UserIdentity user={user} />
                      </td>
                      {renderUserForm(user, "table")}
                    </tr>
                  )
                })}
                {!loading && users.length === 0 ? (
                  <tr>
                    <td className="px-4 py-12 text-center text-muted-foreground" colSpan={7}>暂无用户</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 p-3 xl:hidden">
            {loading && users.length === 0 ? (
              <div className="px-4 py-12 text-center text-muted-foreground">正在加载用户...</div>
            ) : null}
            {users.map((user) => {
              const draft = drafts[user.id] ?? draftFromUser(user)
              return (
                <div key={user.id} className="rounded-lg border border-border bg-card p-4 shadow-xs">
                  <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                    <UserIdentity user={user} />
                    <span className="rounded-full border border-border bg-muted/45 px-2.5 py-1 text-xs text-muted-foreground">
                      {statusLabel(draft.status)}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {renderUserForm(user, "card")}
                  </div>
                </div>
              )
            })}
            {!loading && users.length === 0 ? (
              <div className="px-4 py-12 text-center text-muted-foreground">暂无用户</div>
            ) : null}
          </div>
        </div>
        <OperationLogDialog
          module="user"
          title="用户管理操作日志"
          open={operationLogOpen}
          onOpenChange={setOperationLogOpen}
        />
      </div>
    </div>
  )
}
