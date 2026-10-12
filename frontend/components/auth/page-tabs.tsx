"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { LoaderCircle, Pin, PinOff, X } from "lucide-react"

import { useAuth } from "@/components/auth/auth-provider"
import { getPinnedPageTabs, setPageTabPinned } from "@/lib/api"
import { getVisibleNavigation } from "@/lib/navigation"
import { useSessionQueryState } from "@/lib/session-query-state"
import { cn } from "@/lib/utils"

export function PageTabs() {
  const { user, hasPermission } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [openPaths, setOpenPaths] = useSessionQueryState<string[]>("workspace:manual-tabs", [])
  const [pinnedPaths, setPinnedPaths] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [savingPath, setSavingPath] = useState<string | null>(null)
  const [error, setError] = useState("")
  const activeRef = useRef<HTMLDivElement>(null)
  const navigationRef = useRef<HTMLElement>(null)
  const previousPathnameRef = useRef(pathname)
  const entries = getVisibleNavigation(user, hasPermission).flatMap((group) => group.items)
  if (hasPermission("system.admin")) {
    entries.push({ href: "/admin/mcp-tokens", label: "MCP 令牌管理", icon: Pin, permission: "system.admin" })
  }
  const current = entries.find((entry) => entry.href === pathname)
  const currentPath = current?.href
  const visiblePaths = new Set(entries.map((entry) => entry.href))
  const paths = [...new Set([...pinnedPaths, ...openPaths])]
    .filter((path) => visiblePaths.has(path))

  useEffect(() => {
    let cancelled = false
    getPinnedPageTabs().then((response) => {
      if (!cancelled) {
        setPinnedPaths(response.pinned_paths)
        setLoaded(true)
        setError("")
      }
    }).catch(() => {
      if (!cancelled) setError("固定标签加载失败，请刷新重试")
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [user?.id])

  useEffect(() => {
    if (previousPathnameRef.current === pathname) return
    previousPathnameRef.current = pathname
    if (!currentPath) return
    setOpenPaths((previous) => previous.includes(currentPath) ? previous : [...previous, currentPath])
  }, [pathname, currentPath, setOpenPaths])

  useEffect(() => {
    const navigation = navigationRef.current
    const active = activeRef.current
    if (!navigation || !active) return
    const navigationBounds = navigation.getBoundingClientRect()
    const activeBounds = active.getBoundingClientRect()
    if (activeBounds.left < navigationBounds.left) navigation.scrollLeft += activeBounds.left - navigationBounds.left
    else if (activeBounds.right > navigationBounds.right) navigation.scrollLeft += activeBounds.right - navigationBounds.right
  }, [pathname, pinnedPaths, openPaths])

  async function togglePin(path: string) {
    if (!loaded || loading || savingPath) return
    setSavingPath(path)
    setError("")
    try {
      const response = await setPageTabPinned(path, !pinnedPaths.includes(path))
      setOpenPaths((previous) => previous.includes(path) ? previous : [...previous, path])
      setPinnedPaths(response.pinned_paths)
    } catch {
      setError("固定标签保存失败，请重试")
    } finally {
      setSavingPath(null)
    }
  }

  function closeTab(path: string) {
    if (pinnedPaths.includes(path)) return
    const index = paths.indexOf(path)
    const remaining = paths.filter((item) => item !== path)
    const destination = remaining[Math.max(0, index - 1)]
    setOpenPaths((previous) => previous.filter((item) => item !== path))
    if (path === pathname && destination) router.push(destination, { scroll: false })
  }

  return (
    <header className="sticky top-0 z-[70] h-[var(--page-tabs-height,2.75rem)] border-b border-border bg-muted/95 backdrop-blur-sm">
      <div className="flex h-full items-end gap-1 px-2 md:px-4">
        <div className="flex h-9 shrink-0 items-center px-3 text-xs text-muted-foreground">
          <span className="hidden sm:inline">赫德欢迎您</span>
          <span className="sm:hidden">赫德</span>
        </div>
        <nav ref={navigationRef} aria-label="页面标签" className="flex min-w-0 flex-1 items-end gap-1 overflow-x-auto pt-1">
          {paths.map((path) => {
            const entry = entries.find((item) => item.href === path)!
            const active = path === pathname
            const pinned = pinnedPaths.includes(path)
            return (
              <div
                key={path}
                ref={active ? activeRef : undefined}
                className={cn(
                  "group flex h-9 shrink-0 items-center rounded-t-md border border-b-0 transition-colors",
                  active ? "border-border bg-background text-sky-600 dark:text-sky-400" : "border-transparent text-muted-foreground hover:bg-background/60 hover:text-foreground"
                )}
              >
                <Link href={path} scroll={false} prefetch={false} aria-current={active ? "page" : undefined} className="rounded-tl-md px-3 py-2 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                  {entry.label}
                </Link>
                <button
                  type="button"
                  aria-label={`${pinned ? "取消固定" : "固定"}${entry.label}`}
                  aria-pressed={pinned}
                  title={pinned ? "取消固定标签" : "固定标签到当前账户"}
                  disabled={!loaded || loading || savingPath !== null}
                  onClick={() => void togglePin(path)}
                  className={cn("mr-1 flex size-6 items-center justify-center rounded-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40", pinned ? "text-sky-600 dark:text-sky-400" : "text-muted-foreground/50 hover:text-foreground")}
                >
                  {savingPath === path ? <LoaderCircle className="size-3 animate-spin" /> : pinned ? <PinOff className="size-3" /> : <Pin className="size-3" />}
                </button>
                {!pinned && (
                  <button type="button" aria-label={`关闭${entry.label}`} title="关闭标签" disabled={savingPath === path} onClick={() => closeTab(path)} className="mr-1 flex size-6 items-center justify-center rounded-sm text-muted-foreground/60 outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-30">
                    <X className="size-3" />
                  </button>
                )}
              </div>
            )
          })}
        </nav>
      </div>
      {error && <p role="alert" className="absolute inset-x-0 top-full border-b border-border bg-background px-4 py-1 text-xs text-destructive">{error}</p>}
    </header>
  )
}
