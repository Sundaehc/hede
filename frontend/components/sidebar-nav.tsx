"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { ThemeToggle } from "@/components/theme-toggle"
import { Package, ClipboardList, Truck, Warehouse, Box } from "lucide-react"

const NAV_ITEMS = [
  {
    section: "商品档案",
    items: [
      {
        href: "/products",
        label: "商品信息档案",
        icon: Package,
      },
    ],
  },
  {
    section: "进销存管理",
    items: [
      {
        href: "/inventory",
        label: "进销存记录",
        icon: ClipboardList,
      },
      {
        href: "/suppliers",
        label: "供应商管理",
        icon: Truck,
      },
      {
        href: "/warehouses",
        label: "仓库管理",
        icon: Warehouse,
      },
    ],
  },
]

export function SidebarNav() {
  const pathname = usePathname()

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-svh w-56 flex-col border-r border-sidebar-border bg-sidebar">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
          <Box className="h-4 w-4" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-sidebar-foreground">赫德</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-5 space-y-5">
        {NAV_ITEMS.map((group) => (
          <div key={group.section}>
            <h3 className="mb-1.5 px-2 text-[11px] font-semibold text-muted-foreground tracking-wide">
              {group.section}
            </h3>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = pathname === item.href || pathname.startsWith(item.href + "/")
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
                        isActive
                          ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm"
                          : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                      )}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-r-full bg-sidebar-primary" />
                      )}
                      <item.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isActive ? "text-sidebar-primary" : "text-muted-foreground group-hover:text-sidebar-accent-foreground",
                        )}
                      />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-4 py-3">
        <div className="flex items-center justify-between rounded-lg bg-sidebar-accent/50 px-2 py-1.5">
          <span className="text-xs text-muted-foreground">主题</span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  )
}
