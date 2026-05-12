"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { ThemeToggle } from "@/components/theme-toggle"
import { Package, ClipboardList, Truck, Warehouse } from "lucide-react"

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
    <aside className="fixed left-0 top-0 z-40 flex h-svh w-56 flex-col border-r border-border bg-sidebar">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <span className="font-semibold text-base">商品管理系统</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((group) => (
          <div key={group.section} className="mb-6">
            <h3 className="mb-2 px-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {group.section}
            </h3>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const isActive = pathname === item.href || pathname.startsWith(item.href + "/")
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-sidebar-accent text-sidebar-accent-foreground"
                          : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
                      )}
                    >
                      <item.icon className="h-4 w-4" />
                      {item.label}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border px-4 py-3">
        <ThemeToggle />
      </div>
    </aside>
  )
}
