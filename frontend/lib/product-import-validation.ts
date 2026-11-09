export type ProductImportValidation = {
  code: "product_validation"
  message: string
  total: number
  errors: Array<{
    row_number: number | null
    product_code: string
    brand: string
    summary: string
    reason: string
  }>
}

export function isProductImportValidation(value: unknown): value is ProductImportValidation {
  if (!value || typeof value !== "object") return false
  const detail = value as Partial<ProductImportValidation>
  return detail.code === "product_validation" && typeof detail.message === "string" &&
    Number.isInteger(detail.total) && Array.isArray(detail.errors) && detail.total === detail.errors.length &&
    detail.errors.every((row) => row && (row.row_number === null || Number.isInteger(row.row_number)) &&
      typeof row.product_code === "string" && typeof row.brand === "string" &&
      typeof row.summary === "string" && typeof row.reason === "string")
}
