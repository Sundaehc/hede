"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { LayoutGrid, LoaderCircle, Pin, X } from "lucide-react"

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
    <header className="sticky top-0 z-[70] h-[var(--page-tabs-height,2.75rem)] border-b border-border/70 bg-card/95 shadow-[0_1px_0_0_rgb(0_0_0_/0.02)] backdrop-blur-sm">
      <div className="flex h-full items-center gap-2 px-2 md:gap-3 md:px-4">
        <div className="flex shrink-0 items-center gap-2 border-r border-border/70 pr-2 text-[11px] font-medium text-muted-foreground md:pr-3">
          <LayoutGrid aria-hidden="true" className="size-3.5 text-muted-foreground/65" strokeWidth={1.7} />
          <span className="hidden sm:inline">赫德欢迎您</span>
        </div>
        <nav ref={navigationRef} aria-label="页面标签" className="flex h-full min-w-0 flex-1 items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {paths.map((path) => {
            const entry = entries.find((item) => item.href === path)!
            const active = path === pathname
            const pinned = pinnedPaths.includes(path)
            return (
              <div
                key={path}
                ref={active ? activeRef : undefined}
                className={cn(
                  "group relative flex h-8 shrink-0 items-center rounded-lg border transition-[background-color,border-color,box-shadow] duration-150 motion-reduce:transition-none",
                  active
                    ? "border-sky-200/80 bg-sky-50 text-sky-700 shadow-xs dark:border-sky-400/25 dark:bg-sky-400/10 dark:text-sky-300"
                    : "border-transparent text-muted-foreground hover:border-border/60 hover:bg-muted/70 hover:text-foreground"
                )}
              >
                <Link
                  href={path}
                  scroll={false}
                  prefetch={false}
                  aria-current={active ? "page" : undefined}
                  title={entry.label}
                  className={cn("flex h-full min-w-0 items-center gap-1.5 rounded-l-lg pl-2.5 pr-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring", active ? "font-semibold" : "font-medium")}
                >
                  <entry.icon aria-hidden="true" className={cn("size-3.5 shrink-0", active ? "text-sky-600 dark:text-sky-300" : "text-muted-foreground/65")} strokeWidth={1.7} />
                  <span className="max-w-36 truncate">{entry.label}</span>
                </Link>
                <div className="flex shrink-0 items-center gap-0.5 pr-1">
                  <button
                    type="button"
                    aria-label={`${pinned ? "取消固定" : "固定"}${entry.label}`}
                    aria-pressed={pinned}
                    title={pinned ? "已固定到当前账户，点击取消固定" : "固定标签到当前账户"}
                    disabled={!loaded || loading || savingPath !== null}
                    onClick={() => void togglePin(path)}
                    className={cn(
                      "flex size-6 items-center justify-center rounded-md outline-none transition-[color,background-color,opacity] duration-150 focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-30 motion-reduce:transition-none",
                      pinned
                        ? "bg-sky-100/70 text-sky-600 hover:bg-sky-200/70 dark:bg-sky-400/15 dark:text-sky-300 dark:hover:bg-sky-400/25"
                        : "text-muted-foreground/65 hover:bg-sky-100/80 hover:text-sky-600 dark:hover:bg-sky-400/15 dark:hover:text-sky-300",
                      !active && !pinned && savingPath !== path && "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100"
                    )}
                  >
                    {savingPath === path ? <LoaderCircle aria-hidden="true" className="size-3 animate-spin motion-reduce:animate-none" /> : <Pin aria-hidden="true" className={cn("size-3 transition-transform motion-reduce:transition-none", !pinned && "-rotate-45")} strokeWidth={pinned ? 2 : 1.7} />}
                  </button>
                  {!pinned && (
                    <button
                      type="button"
                      aria-label={`关闭${entry.label}`}
                      title="关闭标签"
                      disabled={savingPath === path}
                      onClick={() => closeTab(path)}
                      className="flex size-6 items-center justify-center rounded-md text-muted-foreground/60 outline-none transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-30 motion-reduce:transition-none"
                    >
                      <X aria-hidden="true" className="size-3" strokeWidth={1.7} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </nav>
      </div>
      {error && <p role="alert" className="absolute inset-x-0 top-full border-b border-destructive/20 bg-background px-4 py-2 text-xs text-destructive shadow-sm">{error}</p>}
    </header>
  )
}
