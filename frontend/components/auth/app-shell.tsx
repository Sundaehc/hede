"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"

import { SidebarNav } from "@/components/sidebar-nav"
import { useAuth } from "@/components/auth/auth-provider"


const AUTH_PATHS = new Set(["/login", "/register"])


export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { loading, user } = useAuth()
  const isAuthPage = AUTH_PATHS.has(pathname)

  useEffect(() => {
    document.body.style.pointerEvents = ""
    document.body.style.overflow = ""
    document.body.removeAttribute("data-scroll-locked")
  }, [pathname, user?.id])

  useEffect(() => {
    if (loading) return
    if (!user && !isAuthPage) {
      router.replace("/login")
      return
    }
    if (user && isAuthPage) {
      router.replace("/products")
    }
  }, [isAuthPage, loading, router, user])

  if (loading && !isAuthPage) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background text-sm text-muted-foreground">
        正在验证登录状态...
      </div>
    )
  }

  if (isAuthPage) {
    return <main className="min-h-svh">{children}</main>
  }

  return (
    <div className="flex min-h-svh">
      <SidebarNav />
      <main className="min-w-0 flex-1 pl-56">{children}</main>
    </div>
  )
}
