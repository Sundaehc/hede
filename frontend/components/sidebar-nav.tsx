"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import { Package, ClipboardList, Truck, Warehouse, Store, Box, BadgeDollarSign, TableProperties, ShoppingCart, UserCog, LogOut } from "lucide-react"

const NAV_ITEMS = [
  {
    section: "商品档案",
    items: [
      {
        href: "/products",
        label: "商品信息档案",
        icon: Package,
        permission: "product.view",
      },
      {
        href: "/fine-table",
        label: "商品精细表",
        icon: TableProperties,
        permission: "fine_table.view",
      },
    ],
  },
  {
    section: "采购单管理",
    items: [
      {
        href: "/purchase-orders",
        label: "采购单管理",
        icon: ShoppingCart,
        permission: "purchase.view",
      },
    ],
  },
  {
    section: "进销存管理",
    items: [
      {
        href: "/inventory",
        label: "经营历程",
        icon: ClipboardList,
        permission: "inventory.view",
      },
      {
        href: "/inventory-purchase-details",
        label: "商品进货明细",
        icon: Package,
        permission: "inventory.view",
      },
      {
        href: "/suppliers",
        label: "供应商管理",
        icon: Truck,
        permission: "inventory.view",
      },
      {
        href: "/warehouses",
        label: "仓库管理",
        icon: Warehouse,
        permission: "inventory.view",
      },
      {
        href: "/general-customer-shops",
        label: "一般客户",
        icon: Store,
        permission: "inventory.view",
      },
      {
        href: "/account-subjects",
        label: "科目管理",
        icon: BadgeDollarSign,
        permission: "inventory.view",
      },
    ],
  },
  {
    section: "系统管理",
    items: [
      {
        href: "/admin",
        label: "用户管理",
        icon: UserCog,
        permission: "system.admin",
      },
    ],
  },
]

export function SidebarNav() {
  const pathname = usePathname()
  const { hasPermission, logout, user } = useAuth()
  const visibleGroups = NAV_ITEMS.map((group) => ({
    ...group,
    items: group.items.filter((item) => hasPermission(item.permission)),
  })).filter((group) => group.items.length > 0)

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-svh w-56 flex-col border-r border-sidebar-border bg-sidebar shadow-2xl shadow-black/10">
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-sm">
          <Box className="h-4 w-4" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-sidebar-foreground">赫德</span>
          <span className="mt-0.5 text-[11px] text-sidebar-foreground/55">商品运营中台</span>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
        {visibleGroups.map((group) => (
          <div key={group.section}>
            <h3 className="mb-2 px-2 text-[11px] font-semibold tracking-wide text-sidebar-foreground/45">
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
                        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-150",
                        isActive
                          ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm shadow-black/10"
                          : "text-sidebar-foreground/75 hover:bg-sidebar-accent/55 hover:text-sidebar-accent-foreground",
                      )}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-sidebar-primary" />
                      )}
                      <item.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isActive ? "text-sidebar-primary" : "text-sidebar-foreground/45 group-hover:text-sidebar-accent-foreground",
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

      <div className="space-y-3 border-t border-sidebar-border px-4 py-3">
        <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/45 px-3 py-2">
          <p className="truncate text-xs font-medium text-sidebar-foreground">{user?.display_name || user?.username}</p>
          <p className="mt-0.5 truncate text-[11px] text-sidebar-foreground/55">{user?.department_name}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-2 h-7 w-full justify-start px-2 text-sidebar-foreground/70 hover:bg-sidebar-accent"
            onClick={() => void logout()}
          >
            <LogOut className="h-3.5 w-3.5" />
            退出登录
          </Button>
        </div>
        <div className="flex items-center justify-between rounded-xl border border-sidebar-border bg-sidebar-accent/45 px-3 py-2">
          <span className="text-xs text-sidebar-foreground/60">主题</span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  )
}
