import { describe, expect, it } from "vitest"

import {
  getAiQueryPrimaryHref,
  getAiQuerySuggestionHref,
} from "@/lib/ai-query-navigation"

describe("getAiQuerySuggestionHref", () => {
  const productGoodsResponse = {
    intent: "product_goods",
    link: {
      label: "打开商品货品表",
      href: "/product-goods?brand=cbanner_mens&query=C7763373D24,C7763372D01&view=goods",
    },
    rows: [],
  }

  it("opens the matching product archive with current result context", () => {
    expect(
      getAiQuerySuggestionHref(productGoodsResponse, "查看这批商品的商品档案")
    ).toBe(
      "/products?brand=cbanner_mens&query=C7763373D24%2CC7763372D01"
    )
  })

  it("keeps unrelated suggestions as natural-language queries", () => {
    expect(
      getAiQuerySuggestionHref(productGoodsResponse, "比较直播和清仓占比")
    ).toBeNull()
  })

  it("uses result goods codes when a ranking link has no query", () => {
    const rankingResponse = {
      intent: "product_goods",
      link: {
        label: "打开商品货品表",
        href: "/product-goods?brand=cbanner_womens&view=goods",
      },
      rows: [
        { goods_code: "RBH63928D25", recent_sales: 489 },
        { goods_code: "R6161539DH9", recent_sales: 412 },
      ],
    }

    expect(getAiQueryPrimaryHref(rankingResponse)).toBe(
      "/product-goods?brand=cbanner_womens&view=goods&query=RBH63928D25%2CR6161539DH9"
    )
    expect(
      getAiQuerySuggestionHref(rankingResponse, "查看这批商品的商品档案")
    ).toBe(
      "/products?brand=cbanner_womens&query=RBH63928D25%2CR6161539DH9"
    )
  })
})
