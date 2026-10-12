"use client"

import { useEffect, useState } from "react"

import { SearchableFilterInput, type SearchableFilterOption } from "@/components/inventory-admin/searchable-filter-input"
import { listInventoryDetailCandidates } from "@/lib/api"

type CandidateSearchResult = {
  query: string
  options: SearchableFilterOption[]
  failed: boolean
}

type InventoryProductCodeFilterProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
}

export function InventoryProductCodeFilter({ id, value, onChange, onSubmit }: InventoryProductCodeFilterProps) {
  const query = value.trim()
  const [result, setResult] = useState<CandidateSearchResult | null>(null)

  useEffect(() => {
    if (query.length < 2) return

    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        const response = await listInventoryDetailCandidates({ query, limit: 20 })
        const options = new Map<string, SearchableFilterOption>()
        for (const candidate of response.items) {
          if (!candidate.product_code || options.has(candidate.product_code)) continue
          options.set(candidate.product_code, {
            value: candidate.product_code,
            label: candidate.product_code,
            keywords: [candidate.sku, candidate.original_sku, candidate.factory_code, candidate.product_name, candidate.color_name].join(" "),
          })
        }
        if (!cancelled) setResult({ query, options: [...options.values()], failed: false })
      } catch {
        if (!cancelled) setResult({ query, options: [], failed: true })
      }
    }, 220)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query])

  const currentResult = query.length >= 2 && result?.query === query ? result : null
  const emptyText = query.length < 2
    ? "输入至少 2 个字符匹配商品编码"
    : !currentResult
      ? "匹配中..."
      : currentResult.failed
        ? "候选加载失败，可直接输入编码搜索"
        : "没有匹配商品，可直接输入编码搜索"

  return (
    <SearchableFilterInput
      id={id}
      value={value}
      options={currentResult?.options ?? []}
      onChange={onChange}
      onSubmit={onSubmit}
      placeholder="商品编码"
      emptyText={emptyText}
    />
  )
}
