import type { AiQueryResponse } from "@/lib/types"

type SuggestionContext = Pick<AiQueryResponse, "intent" | "link" | "rows">

const RESULT_CODE_KEYS = [
  "goods_code",
  "sku",
  "product_code",
  "货号",
  "商品货号",
  "商品编码",
]
const FINE_TABLE_BRANDS = new Set([
  "cbanner_mens",
  "cbanner_womens",
  "yandou",
  "eblan",
])

function resultQuery(rows: AiQueryResponse["rows"]) {
  return Array.from(
    new Set(
      rows.flatMap((row) => {
        for (const key of RESULT_CODE_KEYS) {
          const value = row[key]
          if (typeof value === "string" && value.trim()) return [value.trim()]
        }
        return []
      })
    )
  ).join(",")
}

function sourceWithResultQuery(response: SuggestionContext) {
  if (!response.link?.href) return null
  const source = new URL(response.link.href, "http://localhost")
  if (!source.searchParams.get("query")) {
    const query = resultQuery(response.rows)
    if (query) source.searchParams.set("query", query)
  }
  return source
}

function buildHref(
  pathname: string,
  source: URL,
  extra: Record<string, string> = {}
) {
  const search = new URLSearchParams()
  const brand = source.searchParams.get("brand")
  const query = source.searchParams.get("query")
  if (!brand) return null
  search.set("brand", brand)
  if (query) search.set("query", query)
  for (const [key, value] of Object.entries(extra)) search.set(key, value)
  return `${pathname}?${search.toString()}`
}

export function getAiQuerySuggestionHref(
  response: SuggestionContext,
  suggestion: string
) {
  const source = sourceWithResultQuery(response)
  if (!source) return null
  if (response.intent === "product_goods") {
    if (suggestion === "查看这批商品的商品档案") {
      return buildHref("/products", source)
    }
  }

  if (
    response.intent === "product_archive" &&
    ["查看这批商品近7天销量", "查看这些商品的库存和在途"].includes(suggestion)
  ) {
    return buildHref("/product-goods", source, { view: "goods" })
  }

  return null
}

export function getAiQueryPrimaryHref(response: SuggestionContext) {
  const source = sourceWithResultQuery(response)
  if (!source) return null
  return `${source.pathname}${source.search}${source.hash}`
}

export function getAiQueryFineTableHref(response: SuggestionContext) {
  if (!["product_goods", "product_archive"].includes(response.intent)) {
    return null
  }
  const source = sourceWithResultQuery(response)
  if (!source) return null
  const brand = source.searchParams.get("brand")
  if (!brand || !FINE_TABLE_BRANDS.has(brand)) return null
  return buildHref("/fine-table", source)
}
