export type PostedProductChangeWarning = {
  code: "posted_product_change_confirmation"
  message: string
  confirmation_token: string
  document_count: number
  detail_count: number
  changes: Array<{ field: "sku" | "size_range"; label: string; before: string; after: string }>
  documents: Array<{ id: number; document_number: string | null; document_type: string | null; date: string | null; detail_count: number }>
}

export function isPostedProductChangeWarning(value: unknown): value is PostedProductChangeWarning {
  if (!value || typeof value !== "object") return false
  const detail = value as Partial<PostedProductChangeWarning>
  return detail.code === "posted_product_change_confirmation" && typeof detail.message === "string" &&
    typeof detail.confirmation_token === "string" && /^[a-f0-9]{64}$/.test(detail.confirmation_token) &&
    Number.isInteger(detail.document_count) && Number.isInteger(detail.detail_count) &&
    Array.isArray(detail.changes) && detail.changes.every((change) => change &&
      ["sku", "size_range"].includes(change.field) && typeof change.label === "string" &&
      typeof change.before === "string" && typeof change.after === "string") &&
    Array.isArray(detail.documents) && detail.documents.length === detail.document_count &&
    detail.documents.every((document) => document && Number.isInteger(document.id) && Number.isInteger(document.detail_count) &&
      (document.document_number === null || typeof document.document_number === "string") &&
      (document.document_type === null || typeof document.document_type === "string") &&
      (document.date === null || typeof document.date === "string"))
}
