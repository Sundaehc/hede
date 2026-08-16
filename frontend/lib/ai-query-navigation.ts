import type { AiQueryResponse } from "@/lib/types"

type SuggestionContext = Pick<AiQueryResponse, "intent" | "link">

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
  if (!response.link?.href) return null

  const source = new URL(response.link.href, "http://localhost")
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
