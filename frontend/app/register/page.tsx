"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { UserPlus } from "lucide-react"

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
          { id: 4, code: "美工部", name: "美工部" },
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
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <UserPlus className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">注册账号</h1>
            <p className="text-xs text-muted-foreground">{hasUsers ? "注册后按部门获得默认权限" : "首个账号会自动成为超级管理员"}</p>
          </div>
        </div>

        <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="register-username">账号</label>
              <Input id="register-username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="register-display-name">姓名</label>
              <Input id="register-display-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="register-department">部门</label>
            <Select id="register-department" value={departmentCode} onChange={(event) => setDepartmentCode(event.target.value)}>
              {departments.map((department) => (
                <option key={department.code} value={department.code}>{department.name}</option>
              ))}
            </Select>
            {departmentCode === "美工部" || departmentCode === "design" ? <p className="text-xs text-muted-foreground">美工部默认只可查看商品信息档案。</p> : null}
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="register-password">密码</label>
            <Input id="register-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
          </div>
          {error ? <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p> : null}
          <Button type="submit" className="w-full" disabled={submitting || !username.trim() || !displayName.trim() || !password}>
            {submitting ? "注册中..." : "注册并登录"}
          </Button>
        </form>

        <div className="mt-4 text-center text-xs text-muted-foreground">
          已有账号？<Link className="font-medium text-primary hover:underline" href="/login">返回登录</Link>
        </div>
      </div>
    </div>
  )
}
