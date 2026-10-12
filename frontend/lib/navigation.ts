import {
  Package,
  ClipboardList,
  Truck,
  Warehouse,
  Store,
  BadgeDollarSign,
  TableProperties,
  ShoppingCart,
  UserCog,
  Rows3,
  ChartNoAxesCombined,
  Ruler,
  Palette,
  ListFilter,
  Tags,
  Activity,
} from "lucide-react"

import { hasProductGoodsDepartmentAccess } from "@/lib/product-goods-access"
import type { AuthUser } from "@/lib/types"

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
    section: "其他管理",
    items: [
      {
        href: "/size-groups",
        label: "尺码组管理",
        icon: Ruler,
        permission: "product.view",
      },
      {
        href: "/color-barcodes",
        label: "颜色管理",
        icon: Palette,
        permission: "product.view",
      },
      {
        href: "/auxiliary-attributes",
        label: "辅助属性管理",
        icon: ListFilter,
        permission: "product.view",
      },
      {
        href: "/product-tags",
        label: "商品标签",
        icon: Tags,
        permission: "product.view",
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
        href: "/scheduled-tasks",
        label: "定时任务",
        icon: Activity,
        permission: "system.admin",
      },
    ],
  },
]

export function getVisibleNavigation(
  user: Pick<AuthUser, "role_code" | "department_code"> | null,
  hasPermission: (permission: string) => boolean
) {
  const canAccessProductGoods = hasProductGoodsDepartmentAccess(user)
  const canAccessSizeGroups =
    user?.role_code === "super_admin" ||
    ["商品部", "开发部"].includes(user?.department_code ?? "")
  const canAccessColorManagement =
    user?.role_code === "super_admin" ||
    ["商品部", "开发部"].includes(user?.department_code ?? "")
  const canAccessAuxiliaryAttributes = canAccessColorManagement
  const canAccessProductTags = user?.role_code === "super_admin" || user?.department_code === "开发部"
  const canAccessScheduledTasks =
    user?.role_code === "super_admin" || user?.department_code === "开发部"
  const isProductDepartment =
    user?.role_code !== "super_admin" && user?.department_code === "商品部"
  return NAV_ITEMS.map((group) => ({
    ...group,
    items: group.items.filter(
      (item) =>
        (item.href === "/scheduled-tasks"
          ? canAccessScheduledTasks
          : hasPermission(item.permission)) &&
        (!["/product-goods", "/factory-channel-dashboard"].includes(
          item.href
        ) ||
          canAccessProductGoods) &&
        (item.href !== "/size-groups" || canAccessSizeGroups) &&
        (item.href !== "/color-barcodes" || canAccessColorManagement) &&
        (item.href !== "/auxiliary-attributes" ||
          canAccessAuxiliaryAttributes) &&
        (item.href !== "/product-tags" || canAccessProductTags) &&
        (item.href !== "/scheduled-tasks" || canAccessScheduledTasks) &&
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
}
