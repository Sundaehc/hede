export const PURCHASE_DETAIL_COLUMNS = [
  { key: "product_code", label: "商品货号", width: 130 },
  { key: "remark", label: "商品备注", width: 120 },
  { key: "image_code", label: "图片", width: 130 },
  { key: "factory_code", label: "工厂货号", width: 96 },
  { key: "style_code", label: "款号（鞋内丝印）", width: 140 },
  { key: "inner_color_code", label: "色号（鞋内丝印）", width: 128 },
  { key: "color_name", label: "颜色名称", width: 104 },
  { key: "upper_material", label: "鞋面材质", width: 112 },
  { key: "lining_material", label: "内里材质", width: 112 },
  { key: "outsole_material", label: "大底材质", width: 112 },
  { key: "insole_material", label: "鞋垫材质", width: 112 },
  { key: "shoe_box_spec", label: "鞋盒规格", width: 104 },
  { key: "execution_standard", label: "执行标准", width: 160 },
  { key: "sizes", label: "尺码数量", width: 48 },
  { key: "quantity", label: "数量", width: 72 },
  { key: "unit_price", label: "单价", width: 72 },
  { key: "amount", label: "金额", width: 82 },
] as const

export type PurchaseDetailColumnKey =
  (typeof PURCHASE_DETAIL_COLUMNS)[number]["key"]
export const DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER = PURCHASE_DETAIL_COLUMNS.map(
  ({ key }) => key
)

export function normalizePurchaseDetailColumnOrder(
  value: unknown
): PurchaseDetailColumnKey[] {
  const keys = new Set<string>(DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER)
  const saved = Array.isArray(value)
    ? value.filter(
        (key): key is PurchaseDetailColumnKey =>
          typeof key === "string" && keys.has(key)
      )
    : []
  return [...new Set([...saved, ...DEFAULT_PURCHASE_DETAIL_COLUMN_ORDER])]
}

export function movePurchaseDetailColumn(
  order: PurchaseDetailColumnKey[],
  source: PurchaseDetailColumnKey,
  target: PurchaseDetailColumnKey
) {
  const next = [...order]
  const from = next.indexOf(source),
    to = next.indexOf(target)
  if (from < 0 || to < 0 || from === to) return order
  next.splice(from, 1)
  next.splice(to, 0, source)
  return next
}
