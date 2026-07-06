"use client"

import Link from "next/link"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { AlertCircle, ArrowRight, KeyRound, Loader2, LogIn, UserRound } from "lucide-react"

import { AuthPageShell } from "@/components/auth/auth-page-shell"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { login } from "@/lib/api"


export default function LoginPage() {
  const router = useRouter()
  const { setUser } = useAuth()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
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
      footer={(
        <>
          没有账号？<Link className="font-medium text-primary hover:underline" href="/register">注册账号</Link>
        </>
      )}
    >
      <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="login-username">
            <UserRound className="size-3.5" />
            账号
          </label>
          <Input
            id="login-username"
            className="h-10"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="请输入账号"
          />
        </div>
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground" htmlFor="login-password">
            <KeyRound className="size-3.5" />
            密码
          </label>
          <Input
            id="login-password"
            className="h-10"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            placeholder="请输入密码"
          />
        </div>
        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}
        <Button type="submit" size="lg" className="h-10 w-full justify-between px-3" disabled={submitting || !username.trim() || !password}>
          <span>{submitting ? "登录中..." : "登录"}</span>
          {submitting ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
        </Button>
      </form>
    </AuthPageShell>
  )
}
