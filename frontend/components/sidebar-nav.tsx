"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { listProductGoods } from "@/lib/api"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  Package,
  ClipboardList,
  Truck,
  Warehouse,
  Store,
  Box,
  BadgeDollarSign,
  TableProperties,
  ShoppingCart,
  UserCog,
  LogOut,
  Rows3,
  ChartNoAxesCombined,
  Ruler,
  Sparkles,
} from "lucide-react"

const NAV_ITEMS = [
  {
    section: "商品档案",
    items: [
      {
        href: "/ai-query",
        label: "智能查询",
        icon: Sparkles,
        permission: "ai_query.view",
      },
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
      {
        href: "/product-goods",
        label: "商品货品表",
        icon: Rows3,
        permission: "product.view",
      },
      {
        href: "/factory-channel-dashboard",
        label: "工厂渠道看板",
        icon: ChartNoAxesCombined,
        permission: "product.view",
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
        href: "/supplier-brands",
        label: "品牌管理",
        icon: BadgeDollarSign,
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
      {
        href: "/size-groups",
        label: "尺码组管理",
        icon: Ruler,
        permission: "product.view",
      },
    ],
  },
]

let productGoodsPrefetchStarted = false

function prefetchDefaultProductGoodsPage() {
  if (productGoodsPrefetchStarted) return
  productGoodsPrefetchStarted = true
  void listProductGoods({
    brand: "cbanner_mens",
    page: 1,
    pageSize: 50,
  }).catch(() => {
    // A later page request remains available when this optional warm-up fails.
    productGoodsPrefetchStarted = false
  })
}

export function SidebarNav() {
  const pathname = usePathname()
  const { hasPermission, logout, user } = useAuth()
  const canAccessProductGoods =
    user?.role_code === "super_admin" ||
    ["商品部", "开发部", "运营部"].includes(user?.department_code ?? "")
  const canAccessSizeGroups =
    user?.role_code === "super_admin" ||
    ["商品部", "开发部"].includes(user?.department_code ?? "")
  const canAccessAiQuery =
    user?.role_code === "super_admin" ||
    [
      "ai_query.view",
      "product.view",
      "fine_table.view",
      "purchase.view",
      "inventory.view",
    ].some((permission) => hasPermission(permission))
  const isProductDepartment =
    user?.role_code !== "super_admin" && user?.department_code === "商品部"
  const userName = user?.display_name || user?.username || "未登录用户"
  const userInitial = userName.trim().slice(0, 1).toUpperCase() || "U"
  const visibleGroups = NAV_ITEMS.map((group) => ({
    ...group,
    items: group.items.filter(
      (item) =>
        (item.href === "/ai-query"
          ? canAccessAiQuery
          : hasPermission(item.permission)) &&
        (!["/product-goods", "/factory-channel-dashboard"].includes(
          item.href
        ) ||
          canAccessProductGoods) &&
        (item.href !== "/size-groups" || canAccessSizeGroups) &&
        (item.href !== "/ai-query" || canAccessAiQuery) &&
        (!isProductDepartment ||
          ![
            "/inventory",
            "/inventory-purchase-details",
            "/warehouses",
            "/general-customer-shops",
            "/account-subjects",
          ].includes(item.href))
    ),
  })).filter((group) => group.items.length > 0)

  return (
    <aside className="fixed top-0 left-0 z-40 flex h-svh w-14 flex-col overflow-hidden rounded-r-2xl border-r border-sidebar-border bg-sidebar shadow-2xl shadow-black/10 transition-[width] md:w-56 md:rounded-r-4xl">
      <div className="flex h-16 items-center justify-center gap-3 border-b border-sidebar-border px-2 md:justify-start md:px-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-sm">
          <Box className="h-4 w-4" />
        </div>
        <div className="hidden flex-col leading-tight md:flex">
          <span className="text-sm font-semibold text-sidebar-foreground">
            赫德
          </span>
          <span className="mt-0.5 text-[11px] text-sidebar-foreground/55">
            商品运营中台
          </span>
        </div>
      </div>

      <nav className="sidebar-scroll-area flex-1 space-y-2 overflow-y-auto px-2 py-3 md:space-y-5 md:px-3 md:py-5">
        {visibleGroups.map((group) => (
          <div key={group.section}>
            <h3 className="mb-2 hidden px-2 text-[11px] font-semibold tracking-wide text-sidebar-foreground/45 md:block">
              {group.section}
            </h3>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const isActive =
                  pathname === item.href || pathname.startsWith(item.href + "/")
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onMouseEnter={() => {
                        if (item.href === "/product-goods")
                          prefetchDefaultProductGoodsPage()
                      }}
                      onFocus={() => {
                        if (item.href === "/product-goods")
                          prefetchDefaultProductGoodsPage()
                      }}
                      title={item.label}
                      className={cn(
                        "group relative flex items-center justify-center gap-3 rounded-xl px-2 py-2.5 text-sm font-medium transition-all duration-150 md:justify-start md:px-3",
                        isActive
                          ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm shadow-black/10"
                          : "text-sidebar-foreground/75 hover:bg-sidebar-accent/55 hover:text-sidebar-accent-foreground"
                      )}
                    >
                      {isActive && (
                        <span className="absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-sidebar-primary" />
                      )}
                      <item.icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          isActive
                            ? "text-sidebar-primary"
                            : "text-sidebar-foreground/45 group-hover:text-sidebar-accent-foreground"
                        )}
                      />
                      <span className="hidden truncate md:inline">
                        {item.label}
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border/80 bg-sidebar/80 px-2 py-3 md:px-3">
        <div className="flex min-w-0 flex-col items-center gap-2 md:flex-row md:px-1">
          <div className="relative flex size-8 shrink-0 items-center justify-center rounded-lg border border-sidebar-border bg-sidebar-accent text-xs font-semibold text-sidebar-foreground shadow-sm">
            {userInitial}
            <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full border-2 border-sidebar bg-emerald-400" />
          </div>
          <div className="hidden min-w-0 flex-1 md:block">
            <p className="truncate text-xs font-semibold text-sidebar-foreground">
              {userName}
            </p>
            <p className="mt-0.5 truncate text-[11px] text-sidebar-foreground/55">
              {user?.department_name || "未分配部门"}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-sidebar-foreground/55 hover:bg-destructive/15 hover:text-destructive"
            onClick={() => void logout()}
            title="退出登录"
            aria-label="退出登录"
          >
            <LogOut className="size-3.5" />
          </Button>
        </div>
        <div className="mt-3 flex items-center justify-center border-t border-sidebar-border/70 pt-2 md:h-9 md:justify-between">
          <span className="hidden text-[11px] font-medium text-sidebar-foreground/55 md:inline">
            界面主题
          </span>
          <ThemeToggle className="size-7 rounded-md border-sidebar-border bg-sidebar-accent text-sidebar-foreground shadow-none hover:bg-sidebar-primary hover:text-sidebar-primary-foreground" />
        </div>
      </div>
    </aside>
  )
}
