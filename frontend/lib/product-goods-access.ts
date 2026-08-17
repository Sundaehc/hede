import type { AuthUser } from "@/lib/types"

const PRODUCT_GOODS_DEPARTMENTS = new Set(["商品部", "开发部", "运营部"])

export function hasProductGoodsDepartmentAccess(
  user: Pick<AuthUser, "role_code" | "department_code"> | null
) {
  return (
    user?.role_code === "super_admin" ||
    PRODUCT_GOODS_DEPARTMENTS.has(user?.department_code ?? "")
  )
}
