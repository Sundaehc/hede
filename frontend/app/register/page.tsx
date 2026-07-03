"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AlertCircle, ArrowRight, BadgeCheck, Building2, KeyRound, Loader2, UserPlus, UserRound } from "lucide-react"

import { AuthPageShell } from "@/components/auth/auth-page-shell"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { getAuthOptions, register } from "@/lib/api"
import type { AuthDepartment } from "@/lib/types"


export default function RegisterPage() {
  const router = useRouter()
  const { setUser } = useAuth()
  const [departments, setDepartments] = useState<AuthDepartment[]>([])
  const [hasUsers, setHasUsers] = useState(true)
  const [username, setUsername] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [departmentCode, setDepartmentCode] = useState("商品部")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    async function loadOptions() {
      try {
        const response = await getAuthOptions()
        setDepartments(response.departments)
        setHasUsers(response.has_users)
        setDepartmentCode(response.departments[0]?.code ?? "商品部")
      } catch {
        setDepartments([
          { id: 1, code: "财务部", name: "财务部" },
          { id: 2, code: "商品部", name: "商品部" },
          { id: 3, code: "运营部", name: "运营部" },
          { id: 4, code: "开发部", name: "开发部" },
          { id: 5, code: "美工部", name: "美工部" },
        ])
      }
    }
    void loadOptions()
  }, [])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    try {
      const response = await register({
        username,
        password,
        display_name: displayName,
        department_code: departmentCode,
      })
      setUser(response.user)
      router.replace("/products")
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthPageShell
      badge="账号注册"
      title="注册账号"
      description={hasUsers ? "注册后按部门获得默认权限。" : "首个账号会自动成为超级管理员。"}
      icon={UserPlus}
      footer={(
        <>
          已有账号？<Link className="font-medium text-primary hover:underline" href="/login">返回登录</Link>
        </>
      )}
    >
      <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="register-username">
              <UserRound className="size-3.5" />
              账号
            </label>
            <Input
              id="register-username"
              className="h-10"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="登录账号"
            />
          </div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="register-display-name">
              <BadgeCheck className="size-3.5" />
              姓名
            </label>
            <Input
              id="register-display-name"
              className="h-10"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="真实姓名"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="register-department">
            <Building2 className="size-3.5" />
            部门
          </label>
          <Select id="register-department" className="h-10" value={departmentCode} onChange={(event) => setDepartmentCode(event.target.value)}>
            {departments.map((department) => (
              <option key={department.code} value={department.code}>{department.name}</option>
            ))}
          </Select>
          {departmentCode === "美工部" || departmentCode === "design" ? (
            <p className="text-xs text-muted-foreground">美工部默认只可查看商品信息档案。</p>
          ) : null}
        </div>
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="register-password">
            <KeyRound className="size-3.5" />
            密码
          </label>
          <Input
            id="register-password"
            className="h-10"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            placeholder="设置登录密码"
          />
        </div>
        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}
        <Button type="submit" size="lg" className="h-10 w-full justify-between px-3" disabled={submitting || !username.trim() || !displayName.trim() || !password}>
          <span>{submitting ? "注册中..." : "注册并登录"}</span>
          {submitting ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
        </Button>
      </form>
    </AuthPageShell>
  )
}
