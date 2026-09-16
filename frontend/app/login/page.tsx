"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  LogIn,
  UserRound,
} from "lucide-react"

import { AuthPageShell } from "@/components/auth/auth-page-shell"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { login } from "@/lib/api"


export default function LoginPage() {
  const router = useRouter()
  const { setUser } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const username = String(formData.get("username") ?? "").trim()
    const password = String(formData.get("password") ?? "").trim()
    if (!username || !password) {
      setError("请输入账号和密码")
      return
    }
    setSubmitting(true)
    setError("")
    try {
      const response = await login({ username, password })
      setUser(response.user)
      router.replace("/products")
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthPageShell
      title="登录赫德系统"
      description="使用账号进入商品运营中台。"
      icon={LogIn}
      footer="账号由管理员统一创建"
    >
      <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="login-username">
            <UserRound className="size-3.5" />
            账号
          </label>
          <Input
            id="login-username"
            name="username"
            className="h-10"
            autoComplete="username"
            placeholder="请输入账号"
            required
          />
        </div>
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="login-password">
            <KeyRound className="size-3.5" />
            密码
          </label>
          <div className="relative">
            <Input
              id="login-password"
              name="password"
              className="h-10 pr-10"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="请输入密码"
              required
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex w-10 cursor-pointer items-center justify-center rounded-r-lg text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              aria-label={showPassword ? "隐藏密码" : "显示密码"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((visible) => !visible)}
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}
        <Button type="submit" size="lg" className="h-10 w-full justify-between px-3" disabled={submitting}>
          <span>{submitting ? "登录中..." : "登录"}</span>
          {submitting ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
        </Button>
      </form>
    </AuthPageShell>
  )
}
