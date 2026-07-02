"use client"

import { useEffect, useMemo, useState } from "react"
import { ShieldCheck, RefreshCw, Save } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getAuthOptions, listAdminUsers, updateAdminUser } from "@/lib/api"
import type { AuthDepartment, AuthRole, AuthUser } from "@/lib/types"


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


function draftFromUser(user: AuthUser): UserDraft {
  return {
    display_name: user.display_name,
    department_code: user.department_code,
    role_code: user.role_code,
    status: user.status,
    password: "",
  }
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

  const rolesByDepartment = useMemo(() => {
    return roles.reduce<Record<string, AuthRole[]>>((acc, role) => {
      const key = role.department_code ?? "all"
      acc[key] = [...(acc[key] ?? []), role]
      return acc
    }, {})
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
      <div className="app-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">用户管理</h1>
            <p className="page-subtitle">管理登录账号、部门、角色和账号状态</p>
          </div>
          <Button type="button" variant="outline" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            刷新
          </Button>
        </div>

        {message ? <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">{message}</div> : null}

        <div className="surface-panel overflow-hidden">
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4 text-primary" />
              系统账号
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">账号</th>
                  <th className="px-4 py-3 text-left font-medium">姓名</th>
                  <th className="px-4 py-3 text-left font-medium">部门</th>
                  <th className="px-4 py-3 text-left font-medium">角色</th>
                  <th className="px-4 py-3 text-left font-medium">状态</th>
                  <th className="px-4 py-3 text-left font-medium">新密码</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const draft = drafts[user.id] ?? draftFromUser(user)
                  const availableRoles = [
                    ...(rolesByDepartment.all ?? []),
                    ...(rolesByDepartment[draft.department_code] ?? []),
                  ]
                  return (
                    <tr key={user.id} className="border-t border-border">
                      <td className="px-4 py-3 align-top">
                        <p className="font-medium">{user.username}</p>
                        <p className="mt-1 text-xs text-muted-foreground">ID {user.id}</p>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <Input value={draft.display_name} onChange={(event) => updateDraft(user.id, { display_name: event.target.value })} />
                      </td>
                      <td className="px-4 py-3 align-top">
                        <Select value={draft.department_code} onChange={(event) => updateDraft(user.id, { department_code: event.target.value })}>
                          {departments.map((department) => (
                            <option key={department.code} value={department.code}>{department.name}</option>
                          ))}
                        </Select>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <Select value={draft.role_code} onChange={(event) => updateDraft(user.id, { role_code: event.target.value })}>
                          {availableRoles.map((role) => (
                            <option key={role.code} value={role.code}>{role.name}</option>
                          ))}
                        </Select>
                        <p className="mt-1 text-xs text-muted-foreground">{availableRoles.find((role) => role.code === draft.role_code)?.description}</p>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <Select value={draft.status} onChange={(event) => updateDraft(user.id, { status: event.target.value })}>
                          {STATUS_OPTIONS.map((status) => (
                            <option key={status.value} value={status.value}>{status.label}</option>
                          ))}
                        </Select>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <Input type="password" value={draft.password} placeholder="留空不修改" onChange={(event) => updateDraft(user.id, { password: event.target.value })} />
                      </td>
                      <td className="px-4 py-3 text-right align-top">
                        <Button type="button" size="sm" onClick={() => void saveUser(user)} disabled={savingId === user.id}>
                          <Save className="h-3.5 w-3.5" />
                          {savingId === user.id ? "保存中" : "保存"}
                        </Button>
                      </td>
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
        </div>
      </div>
    </div>
  )
}
