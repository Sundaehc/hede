export const BRANDS = [
  { key: "all", label: "总览" },
  { key: "cbanner_mens", label: "千百度男鞋" },
  { key: "cbanner_womens", label: "千百度女鞋" },
  { key: "yandou", label: "烟斗" },
  { key: "eblan", label: "伊伴" },
] as const

export type BrandKey = (typeof BRANDS)[number]["key"]

export const PRODUCT_ARCHIVE_BRANDS = [
  ...BRANDS,
  { key: "smiley", label: "笑脸" },
  { key: "ni", label: "NI" },
] as const

export type ProductArchiveBrandKey = string
export type ProductArchiveRecordBrandKey = Exclude<ProductArchiveBrandKey, "all">
export type ProductArchiveBrand = {
  key: ProductArchiveBrandKey
  label: string
}

type ManagedBrand = {
  code: string
  name: string
}

const PRODUCT_ARCHIVE_BRAND_CODES = new Set<string>([
  "cbanner_mens",
  "cbanner_womens",
  "yandou",
  "eblan",
  "smiley",
  "ni",
])

export function resolveProductArchiveBrands(managedBrands: readonly ManagedBrand[]) {
  const staticBrands = PRODUCT_ARCHIVE_BRANDS.filter((brand) => brand.key !== "all") as ProductArchiveBrand[]
  const staticByCode = new Map(staticBrands.map((brand) => [brand.key, brand]))
  const configuredBrands: ProductArchiveBrand[] = []
  const configuredCodes = new Set<string>()

  for (const managedBrand of managedBrands) {
    const code = managedBrand.code
    const staticBrand = staticByCode.get(code)
    if (configuredCodes.has(code)) continue
    configuredCodes.add(code)
    configuredBrands.push({ key: code, label: managedBrand.name || staticBrand?.label || code })
  }

  const unconfiguredBrands: ProductArchiveBrand[] = staticBrands
    .filter((brand) => !configuredCodes.has(brand.key))
    .map((brand) => ({ key: brand.key, label: brand.label }))

  return [
    { key: "all" as const, label: "总览" },
    ...configuredBrands,
    ...unconfiguredBrands,
  ]
}
