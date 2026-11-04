export function productAttributeValues(value: string): string[] {
  let values: unknown[] = [value]
  if (value.trim().startsWith("[")) {
    try {
      const parsed: unknown = JSON.parse(value)
      if (Array.isArray(parsed)) values = parsed
    } catch {
      // Older links and session values may contain plain text.
    }
  }
  return [...new Set(values.flatMap((item) => typeof item === "string" && item.trim() ? [item.trim()] : []))]
}

// Keep existing single-value URLs working; arrays preserve punctuation in names.
export function productAttributeFilter(values: string[], query = ""): string {
  const normalized = [...new Set([...values, query].map((value) => value.trim()).filter(Boolean))]
  if (!normalized.length) return ""
  return normalized.length === 1 && !normalized[0].startsWith("[") ? normalized[0] : JSON.stringify(normalized)
}

export function productAttributeSummary(value: string): string {
  return productAttributeValues(value).join("、")
}
