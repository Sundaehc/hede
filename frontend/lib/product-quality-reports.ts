export type QualityReport = {
  id: string
  name: string
  file_name: string | null
  modified_at: string | null
  status: "matched" | "number_match" | "ambiguous" | "missing"
  sources: Array<{ workbook: string; sheet: string; row: number }>
}

export type QualityReportList = {
  original_sku: string
  items: QualityReport[]
}
