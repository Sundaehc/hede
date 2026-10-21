"use client"

import { useSessionQueryState } from "@/lib/session-query-state"

import Link from "next/link"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { AlertCircle, Ban, Building2, Check, CheckCircle2, Eye, EyeOff, History, Info, Loader2, Plus, RefreshCw, Save, Search, ShieldCheck, Undo2, Users, type LucideIcon } from "lucide-react"
import { Popover } from "radix-ui"

import { useAuth } from "@/components/auth/auth-provider"
import { OperationLogDialog } from "@/components/operation-log-dialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { Select } from "@/components/ui/select"
import { createAdminUser, getAuthOptions, listAdminUsers, updateAdminUser } from "@/lib/api"
import type { AuthDepartment, AuthRole, AuthUser } from "@/lib/types"
import { cn } from "@/lib/utils"


type UserDraft = {
  display_name: string
  department_code: string
  role_code: string
  status: string
  password: string
}

type CreateUserDraft = {
  username: string
  display_name: string
  department_code: string
  role_code: string
  status: string
  password: string
  confirm_password: string
}


const STATUS_OPTIONS = [
  { value: "active", label: "启用" },
  { value: "disabled", label: "禁用" },
]

const PAGE_SIZES = [20, 50, 100]

const STATUS_META = {
  active: {
    label: "启用",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  disabled: {
    label: "禁用",
    className: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/25 dark:bg-rose-500/10 dark:text-rose-300",
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

function buildPageRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1)
  const pages: (number | "ellipsis")[] = [1]
  if (current > 3) pages.push("ellipsis")
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)
  for (let value = start; value <= end; value += 1) pages.push(value)
  if (current < total - 2) pages.push("ellipsis")
  pages.push(total)
  return pages
}

function UserIdentity({ user }: { user: AuthUser }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <div aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-muted/60 text-xs font-semibold text-foreground">
        {userInitial(user)}
      </div>
      <p className="min-w-0 truncate text-[13px] font-semibold text-foreground" title={user.username}>{user.username}</p>
    </div>
  )
}

function RoleDescription({ role, username }: { role: AuthRole | undefined; username: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`查看 ${username} 的角色权限`}
          title="查看角色权限"
          className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring data-[state=open]:bg-muted data-[state=open]:text-foreground"
        >
          <Info aria-hidden="true" className="size-3.5" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          aria-label="角色权限说明"
          align="end"
          sideOffset={6}
          collisionPadding={12}
          className="z-[150] w-72 max-w-[calc(100vw-1.5rem)] rounded-xl border border-border bg-popover p-3.5 text-popover-foreground shadow-lg outline-none"
        >
          <div className="flex items-center gap-2 text-xs font-semibold">
            <ShieldCheck aria-hidden="true" className="size-3.5 text-muted-foreground" />
            {role?.name || "角色权限"}
          </div>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{role?.description || "暂无角色说明"}</p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

function UserPasswordInput({ username, value, onChange, compact = false, disabled = false }: {
  username: string
  value: string
  onChange: (value: string) => void
  compact?: boolean
  disabled?: boolean
}) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="relative min-w-0">
      <Input
        type={visible ? "text" : "password"}
        aria-label={`${username}的新密码`}
        value={value}
        placeholder="留空不修改"
        autoComplete="new-password"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={cn("bg-background pr-9 shadow-none", compact && "h-8 rounded-md px-2 pr-8 text-xs")}
      />
      <button
        type="button"
        aria-label={`${visible ? "隐藏" : "显示"} ${username} 的新密码`}
        aria-pressed={visible}
        disabled={disabled}
        onClick={() => setVisible((current) => !current)}
        className="absolute inset-y-0 right-0 flex w-8 cursor-pointer items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
      >
        {visible ? <EyeOff aria-hidden="true" className="size-3.5" /> : <Eye aria-hidden="true" className="size-3.5" />}
      </button>
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
  const { user: currentUser, hasPermission } = useAuth()
  const [users, setUsers] = useState<AuthUser[]>([])
  const [departments, setDepartments] = useState<AuthDepartment[]>([])
  const [roles, setRoles] = useState<AuthRole[]>([])
  const [drafts, setDrafts] = useState<Record<number, UserDraft>>({})
  const [page, setPage] = useSessionQueryState("users:page", 1)
  const [pageSize, setPageSize] = useSessionQueryState("users:pageSize", PAGE_SIZES[0])
  const [nameInput, setNameInput] = useSessionQueryState("users:nameInput", "")
  const [nameQuery, setNameQuery] = useSessionQueryState("users:nameQuery", "")
  const [total, setTotal] = useState(0)
  const [userStats, setUserStats] = useState({ active: 0, disabled: 0, departmentCount: 0 })
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [message, setMessage] = useState("")
  const [operationLogOpen, setOperationLogOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [showCreatePassword, setShowCreatePassword] = useState(false)
  const [showCreateConfirmPassword, setShowCreateConfirmPassword] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")
  const [createDraft, setCreateDraft] = useState<CreateUserDraft>({
    username: "",
    display_name: "",
    department_code: "",
    role_code: "",
    status: "active",
    password: "",
    confirm_password: "",
  })

  const rolesByDepartment = useMemo(() => {
    return roles.reduce<Record<string, AuthRole[]>>((acc, role) => {
      const key = role.department_code ?? "all"
      acc[key] = [...(acc[key] ?? []), role]
      return acc
    }, {})
  }, [roles])

  const roleByCode = useMemo(() => {
    return Object.fromEntries(roles.map((role) => [role.code, role]))
  }, [roles])

  const createRoleOptions = useMemo(() => [
    ...(rolesByDepartment.all ?? []),
    ...(rolesByDepartment[createDraft.department_code] ?? []),
  ], [createDraft.department_code, rolesByDepartment])

  const load = async (preserveMessage = false) => {
    setLoading(true)
    if (!preserveMessage) setMessage("")
    try {
      const [options, userResponse] = await Promise.all([getAuthOptions(), listAdminUsers({ page, pageSize, nameQuery: nameQuery || undefined })])
      const totalPages = Math.max(1, Math.ceil(userResponse.total / pageSize))
      if (page > totalPages) {
        setPage(totalPages)
        return
      }
      setDepartments(options.departments)
      setRoles(options.roles)
      setUsers(userResponse.items)
      setDrafts(Object.fromEntries(userResponse.items.map((user) => [user.id, draftFromUser(user)])))
      setTotal(userResponse.total)
      setUserStats({
        active: userResponse.stats.active,
        disabled: userResponse.stats.disabled,
        departmentCount: userResponse.stats.department_count,
      })
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
  }, [hasPermission, page, pageSize, nameQuery])

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
      await load(true)
      setMessage("用户已更新")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "保存失败")
    } finally {
      setSavingId(null)
    }
  }

  const openCreateDialog = () => {
    const departmentCode = departments[0]?.code ?? ""
    const availableRoles = [
      ...(rolesByDepartment.all ?? []),
      ...(rolesByDepartment[departmentCode] ?? []),
    ]
    const departmentRole = availableRoles.find((role) => role.department_code === departmentCode)
    setCreateDraft({
      username: "",
      display_name: "",
      department_code: departmentCode,
      role_code: departmentRole?.code ?? availableRoles[0]?.code ?? "",
      status: "active",
      password: "",
      confirm_password: "",
    })
    setCreateError("")
    setShowCreatePassword(false)
    setShowCreateConfirmPassword(false)
    setCreateOpen(true)
  }

  const updateCreateDraft = (patch: Partial<CreateUserDraft>) => {
    setCreateDraft((current) => ({ ...current, ...patch }))
  }

  const changeCreateDepartment = (departmentCode: string) => {
    const availableRoles = [
      ...(rolesByDepartment.all ?? []),
      ...(rolesByDepartment[departmentCode] ?? []),
    ]
    const departmentRole = availableRoles.find((role) => role.department_code === departmentCode)
    updateCreateDraft({
      department_code: departmentCode,
      role_code: departmentRole?.code ?? availableRoles[0]?.code ?? "",
    })
  }

  const submitCreateUser = async () => {
    const username = createDraft.username.trim()
    const displayName = createDraft.display_name.trim()
    if (username.length < 2) {
      setCreateError("账号至少需要 2 个字符")
      return
    }
    if (/\s/.test(username)) {
      setCreateError("账号不能包含空格")
      return
    }
    if (!displayName) {
      setCreateError("请输入姓名")
      return
    }
    if (!createDraft.department_code || !createDraft.role_code) {
      setCreateError("请选择部门和角色")
      return
    }
    if (createDraft.password.length < 8) {
      setCreateError("密码至少需要 8 个字符")
      return
    }
    if (createDraft.password !== createDraft.confirm_password) {
      setCreateError("两次输入的密码不一致")
      return
    }

    setCreating(true)
    setCreateError("")
    try {
      const response = await createAdminUser({
        username,
        display_name: displayName,
        department_code: createDraft.department_code,
        role_code: createDraft.role_code,
        status: createDraft.status,
        password: createDraft.password,
      })
      setCreateOpen(false)
      await load(true)
      setMessage(response.message)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "创建账号失败")
    } finally {
      setCreating(false)
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
        aria-label={`保存账号 ${user.username}`}
        className="h-8 min-w-[76px] rounded-md px-2 shadow-none"
      >
        {isSaving ? <Loader2 aria-hidden="true" className="size-3.5 animate-spin" /> : changed ? <Save aria-hidden="true" className="size-3.5" /> : <Check aria-hidden="true" className="size-3.5" />}
        {isSaving ? "保存中" : changed ? "保存" : "已保存"}
      </Button>
    )
    const resetButton = changed ? (
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        aria-label={`撤销 ${user.username} 的修改`}
        title="撤销本行修改"
        disabled={isSaving}
        onClick={() => setDrafts((current) => ({ ...current, [user.id]: draftFromUser(user) }))}
        className="size-8 rounded-md text-muted-foreground shadow-none"
      >
        <Undo2 aria-hidden="true" className="size-3.5" />
      </Button>
    ) : null
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
          <td className="px-3 py-2.5 align-middle">
            <Input
              aria-label={`${user.username}的姓名`}
              value={draft.display_name}
              disabled={isSaving}
              onChange={(event) => updateDraft(user.id, { display_name: event.target.value })}
              className="h-8 rounded-md bg-background px-2 text-xs shadow-none"
            />
          </td>
          <td className="px-3 py-2.5 align-middle">
            <Select
              aria-label={`${user.username}的部门`}
              value={draft.department_code}
              disabled={isSaving}
              onChange={(event) => changeDepartment(event.target.value)}
              className="h-8 rounded-md bg-background px-2 py-1 text-xs shadow-none"
            >
              {departments.map((department) => (
                <option key={department.code} value={department.code}>{department.name}</option>
              ))}
            </Select>
          </td>
          <td className="px-3 py-2.5 align-middle">
            <div className="flex min-w-0 items-center gap-1">
              <Select
                aria-label={`${user.username}的角色`}
                value={draft.role_code}
                disabled={isSaving}
                onChange={(event) => updateDraft(user.id, { role_code: event.target.value })}
                className="h-8 min-w-0 flex-1 rounded-md bg-background px-2 py-1 text-xs shadow-none"
              >
                {availableRoles.map((role) => (
                  <option key={role.code} value={role.code}>{role.name}</option>
                ))}
              </Select>
              <RoleDescription role={selectedRole} username={user.username} />
            </div>
          </td>
          <td className="px-3 py-2.5 align-middle">
            <Select
              aria-label={`${user.username}的状态`}
              value={draft.status}
              disabled={isSaving}
              onChange={(event) => updateDraft(user.id, { status: event.target.value })}
              className={cn("h-8 rounded-md px-2 py-1 text-xs font-medium shadow-none", getStatusMeta(draft.status).className)}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status.value} value={status.value}>{status.label}</option>
              ))}
            </Select>
          </td>
          <td className="px-3 py-2.5 align-middle">
            <UserPasswordInput
              username={user.username}
              value={draft.password}
              onChange={(password) => updateDraft(user.id, { password })}
              compact
              disabled={isSaving}
            />
          </td>
          <td className={cn("sticky right-0 border-l border-border/60 px-3 py-2.5 text-right align-middle", changed ? "bg-amber-50 dark:bg-amber-950" : "bg-card")}>
            <div className="flex items-center justify-end gap-1">
              {resetButton}
              {saveButton}
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
              aria-label={`${user.username}的姓名`}
              value={draft.display_name}
              disabled={isSaving}
              onChange={(event) => updateDraft(user.id, { display_name: event.target.value })}
              className="h-9 bg-background"
            />
          </div>
          <div>
            <FieldLabel>部门</FieldLabel>
            <Select
              aria-label={`${user.username}的部门`}
              value={draft.department_code}
              disabled={isSaving}
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
            <div className="flex items-center gap-1">
              <Select
                aria-label={`${user.username}的角色`}
                value={draft.role_code}
                disabled={isSaving}
                onChange={(event) => updateDraft(user.id, { role_code: event.target.value })}
                className="h-9 min-w-0 flex-1 bg-background"
              >
                {availableRoles.map((role) => (
                  <option key={role.code} value={role.code}>{role.name}</option>
                ))}
              </Select>
              <RoleDescription role={selectedRole} username={user.username} />
            </div>
          </div>
          <div>
            <FieldLabel>状态</FieldLabel>
            <Select
              aria-label={`${user.username}的状态`}
              value={draft.status}
              disabled={isSaving}
              onChange={(event) => updateDraft(user.id, { status: event.target.value })}
              className={cn("h-9 font-medium", getStatusMeta(draft.status).className)}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status.value} value={status.value}>{status.label}</option>
              ))}
            </Select>
          </div>
          <div>
            <FieldLabel>新密码</FieldLabel>
            <UserPasswordInput
              username={user.username}
              value={draft.password}
              onChange={(password) => updateDraft(user.id, { password })}
              disabled={isSaving}
            />
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
          <span className={cn("text-xs", changed ? "text-amber-700 dark:text-amber-300" : "text-muted-foreground")}>
            {changed ? "有未保存修改" : "所有修改已保存"}
          </span>
          <div className="flex items-center gap-1">{resetButton}{saveButton}</div>
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

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const pageRange = buildPageRange(page, totalPages)
  const changedUserCount = users.filter((user) => hasDraftChanges(user, drafts[user.id] ?? draftFromUser(user))).length

  return (
    <div className="app-page">
      <div className="app-content min-w-0 max-w-[1440px]">
        <div className="page-header">
          <div>
            <h1 className="page-title">用户管理</h1>
            <p className="page-subtitle">管理登录账号、部门、角色和账号状态</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {currentUser?.role_code === "super_admin" ? (
              <Button asChild variant="outline">
                <Link href="/admin/mcp-tokens" scroll={false}>
                  <ShieldCheck className="h-3.5 w-3.5" />
                  MCP Token 管理
                </Link>
              </Button>
            ) : null}
            <Button type="button" onClick={openCreateDialog}>
              <Plus className="h-3.5 w-3.5" />
              创建账号
            </Button>
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
          <StatTile icon={Users} label="账号总数" value={total} />
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

        <section aria-label="系统账号" className="surface-panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3 border-b border-border px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold">系统账号</h2>
                  <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                    {loading ? "正在加载" : `${nameQuery ? "匹配 " : ""}${total} 个账号`}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-muted-foreground">修改后逐行保存，禁用账号将无法登录</p>
              </div>
            </div>
            <form
              className="flex w-full flex-wrap items-center gap-2 md:w-auto"
              onSubmit={(event) => {
                event.preventDefault()
                setPage(1)
                setNameQuery(nameInput.trim())
              }}
            >
              <div className="min-w-0 flex-1 md:w-56 md:flex-none">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="user-name-filter"
                    aria-label="姓名筛选"
                    value={nameInput}
                    onChange={(event) => setNameInput(event.target.value)}
                    placeholder="输入姓名关键词"
                    className="h-8 rounded-lg bg-background pl-9 text-xs shadow-none"
                  />
                </div>
              </div>
              <Button type="submit" className="h-8 px-3 shadow-none" disabled={loading}>查询</Button>
              <Button
                type="button"
                variant="outline"
                className="h-8 px-3 shadow-none"
                disabled={loading || (!nameInput && !nameQuery)}
                onClick={() => {
                  setNameInput("")
                  setNameQuery("")
                  setPage(1)
                }}
              >清空</Button>
            </form>
          </div>

          {changedUserCount > 0 ? (
            <div role="status" className="flex items-center gap-2 border-b border-amber-200/70 bg-amber-50/70 px-4 py-2 text-xs text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300">
              <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-amber-500" />
              当前页有 {changedUserCount} 个账号待保存，请点击对应行的“保存”
            </div>
          ) : null}

          <div className="hidden overflow-x-auto lg:block">
            <table aria-label="系统账号列表" className="w-full min-w-[1060px] table-fixed border-collapse text-sm">
              <colgroup>
                <col className="w-[180px]" />
                <col className="w-[120px]" />
                <col className="w-[125px]" />
                <col className="w-[210px]" />
                <col className="w-[100px]" />
                <col className="w-[165px]" />
                <col className="w-[140px]" />
              </colgroup>
              <thead className="border-b border-border bg-muted/45 text-[11px] text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2.5 text-left font-medium">登录账号</th>
                  <th scope="col" className="px-3 py-2.5 text-left font-medium">姓名</th>
                  <th scope="col" className="px-3 py-2.5 text-left font-medium">所属部门</th>
                  <th scope="col" className="px-3 py-2.5 text-left font-medium">角色 / 权限</th>
                  <th scope="col" className="px-3 py-2.5 text-left font-medium">账号状态</th>
                  <th scope="col" className="px-3 py-2.5 text-left font-medium">重置密码</th>
                  <th scope="col" className="sticky right-0 border-l border-border/60 bg-muted px-3 py-2.5 text-right font-medium">操作</th>
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
                  const changed = hasDraftChanges(user, drafts[user.id] ?? draftFromUser(user))
                  return (
                    <tr key={user.id} data-dirty={changed || undefined} className={cn("transition-colors hover:bg-muted/25", changed ? "bg-amber-50/60 dark:bg-amber-500/5" : "bg-card/40")}>
                      <td className={cn("relative px-3 py-2.5 align-middle", changed && "before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-r before:bg-amber-500")}>
                        <UserIdentity user={user} />
                      </td>
                      {renderUserForm(user, "table")}
                    </tr>
                  )
                })}
                {!loading && users.length === 0 ? (
                  <tr>
                    <td className="px-4 py-12 text-center text-muted-foreground" colSpan={7}>{nameQuery ? "未找到匹配姓名的用户" : "暂无用户"}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div role="group" aria-label="账号卡片" className="grid gap-3 p-3 sm:grid-cols-2 lg:hidden">
            {loading && users.length === 0 ? (
              <div className="px-4 py-12 text-center text-muted-foreground">正在加载用户...</div>
            ) : null}
            {users.map((user) => {
              const changed = hasDraftChanges(user, drafts[user.id] ?? draftFromUser(user))
              return (
                <div key={user.id} className={cn("min-w-0 rounded-xl border bg-card p-3.5 shadow-xs", changed ? "border-amber-300 dark:border-amber-500/40" : "border-border")}>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
                    <UserIdentity user={user} />
                    {changed ? <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">待保存</span> : null}
                  </div>
                  <div className="space-y-3">
                    {renderUserForm(user, "card")}
                  </div>
                </div>
              )
            })}
            {!loading && users.length === 0 ? (
              <div className="px-4 py-12 text-center text-muted-foreground">{nameQuery ? "未找到匹配姓名的用户" : "暂无用户"}</div>
            ) : null}
          </div>

          {total > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>第 {total === 0 ? 0 : (page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} 条，共 {total} 条</span>
                <Select
                  aria-label="每页显示条数"
                  value={String(pageSize)}
                  onChange={(event) => {
                    setPageSize(Number(event.target.value))
                    setPage(1)
                  }}
                  className="h-8 w-20 bg-background text-xs"
                >
                  {PAGE_SIZES.map((size) => <option key={size} value={String(size)}>{size} 条</option>)}
                </Select>
              </div>
              {totalPages > 1 ? (
                <Pagination className="mx-0 w-auto">
                  <PaginationContent>
                    <PaginationItem>
                      <PaginationPrevious
                        text="上一页"
                        onClick={() => setPage((current) => Math.max(1, current - 1))}
                        className={page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                      />
                    </PaginationItem>
                    {pageRange.map((item, index) => item === "ellipsis" ? (
                      <PaginationItem key={`ellipsis-${index}`}><PaginationEllipsis /></PaginationItem>
                    ) : (
                      <PaginationItem key={item}>
                        <PaginationLink
                          isActive={item === page}
                          onClick={() => item !== page && setPage(item)}
                          className={item === page ? "cursor-default" : "cursor-pointer"}
                        >
                          {item}
                        </PaginationLink>
                      </PaginationItem>
                    ))}
                    <PaginationItem>
                      <PaginationNext
                        text="下一页"
                        onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                        className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                      />
                    </PaginationItem>
                  </PaginationContent>
                </Pagination>
              ) : null}
            </div>
          ) : null}
        </section>
        <Dialog
          open={createOpen}
          onOpenChange={(open) => {
            if (!creating) setCreateOpen(open)
          }}
        >
          <DialogContent className="max-w-xl p-0">
            <DialogHeader className="border-b border-border px-6 py-4">
              <DialogTitle>创建账号</DialogTitle>
              <DialogDescription>新账号创建后可立即使用，权限由部门和角色共同决定。</DialogDescription>
            </DialogHeader>
            <form
              className="space-y-5 px-6 py-5"
              onSubmit={(event) => {
                event.preventDefault()
                void submitCreateUser()
              }}
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-username">登录账号</label>
                  <Input
                    id="create-username"
                    value={createDraft.username}
                    onChange={(event) => updateCreateDraft({ username: event.target.value })}
                    placeholder="请输入登录账号"
                    autoComplete="off"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-display-name">姓名</label>
                  <Input
                    id="create-display-name"
                    value={createDraft.display_name}
                    onChange={(event) => updateCreateDraft({ display_name: event.target.value })}
                    placeholder="请输入姓名"
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-department">部门</label>
                  <Select
                    id="create-department"
                    value={createDraft.department_code}
                    onChange={(event) => changeCreateDepartment(event.target.value)}
                  >
                    {departments.map((department) => (
                      <option key={department.code} value={department.code}>{department.name}</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-role">角色</label>
                  <Select
                    id="create-role"
                    value={createDraft.role_code}
                    onChange={(event) => updateCreateDraft({ role_code: event.target.value })}
                  >
                    {createRoleOptions.map((role) => (
                      <option key={role.code} value={role.code}>{role.name}</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-password">初始密码</label>
                  <div className="relative">
                    <Input
                      id="create-password"
                      className="pr-10"
                      type={showCreatePassword ? "text" : "password"}
                      value={createDraft.password}
                      onChange={(event) => updateCreateDraft({ password: event.target.value })}
                      placeholder="至少 8 个字符"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="absolute inset-y-0 right-0 flex w-10 cursor-pointer items-center justify-center rounded-r-lg text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                      aria-label={showCreatePassword ? "隐藏初始密码" : "显示初始密码"}
                      aria-pressed={showCreatePassword}
                      aria-controls="create-password"
                      onClick={() => setShowCreatePassword((visible) => !visible)}
                    >
                      {showCreatePassword ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-confirm-password">确认密码</label>
                  <div className="relative">
                    <Input
                      id="create-confirm-password"
                      className="pr-10"
                      type={showCreateConfirmPassword ? "text" : "password"}
                      value={createDraft.confirm_password}
                      onChange={(event) => updateCreateDraft({ confirm_password: event.target.value })}
                      placeholder="再次输入密码"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="absolute inset-y-0 right-0 flex w-10 cursor-pointer items-center justify-center rounded-r-lg text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                      aria-label={showCreateConfirmPassword ? "隐藏确认密码" : "显示确认密码"}
                      aria-pressed={showCreateConfirmPassword}
                      aria-controls="create-confirm-password"
                      onClick={() => setShowCreateConfirmPassword((visible) => !visible)}
                    >
                      {showCreateConfirmPassword ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground" htmlFor="create-status">账号状态</label>
                  <Select
                    id="create-status"
                    value={createDraft.status}
                    onChange={(event) => updateCreateDraft({ status: event.target.value })}
                  >
                    {STATUS_OPTIONS.map((status) => (
                      <option key={status.value} value={status.value}>{status.label}</option>
                    ))}
                  </Select>
                </div>
              </div>

              {createError ? (
                <div className="flex items-center gap-2 rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{createError}</span>
                </div>
              ) : null}

              <DialogFooter className="border-t border-border pt-4">
                <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>取消</Button>
                <Button type="submit" disabled={creating}>
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  {creating ? "创建中" : "创建账号"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
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
