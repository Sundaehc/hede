import { FIELD_LABELS } from "@/lib/fields"

const OPERATION_LOG_FIELD_LABELS: Record<string, string> = {
  ...FIELD_LABELS,
  document_number: "单据编号",
  date: "日期",
  supplier: "供应商/单位",
  total_count: "总数",
  amount: "金额",
  warehouse: "仓库",
  document_type: "单据类型",
  handler: "经手人",
  summary: "摘要",
  additional_note: "附加说明",
  product_code: "商品编号",
  color_spec: "颜色及规格",
  color_barcode: "颜色条码",
  color_name: "颜色名称",
  size_quantities: "尺码数量",
  quantity: "数量",
  unit_price: "单价",
  remark: "备注",
  extra_fields: "扩展信息",
  brand: "品牌",
  name: "名称",
  factory_code: "工厂代码",
  contact: "联系人",
  wechat: "微信号",
  cooperation_status: "合作状态",
  address: "地址",
  notes: "备注",
  code: "编号",
  customer_name: "品牌名称",
  shop_name: "店铺名称",
  shop_id: "店铺",
  unit_name: "单位名称",
  username: "账号",
  display_name: "姓名",
  department_code: "部门",
  department_name: "部门",
  role_code: "角色",
  role_name: "角色",
  status: "状态",
  password: "密码",
  sort_order: "排序",
  deleted_at: "删除时间",
  items: "尺码明细",
  delivery_date: "到货日期",
  warehouse_code: "仓库编号",
  handler_code: "职员编号",
  image_code: "图片编码",
  inner_color_code: "色号（鞋内丝印）",
  style_code: "款式编码",
  size_labels: "尺码列表",
  size_name: "尺码",
  barcode: "条码",
  product_count: "使用商品数",
  brand_scope: "适用品牌",
  attribute_type: "属性类型",
  attribute_name: "属性值",
  selling_points: "卖点",
}

const DATABASE_FIELD_NAME = /^[a-z][a-z0-9_]*$/

function isDatabaseFieldName(value: string) {
  return DATABASE_FIELD_NAME.test(value.trim())
}

export function getOperationLogFieldLabel(
  field: string,
  savedLabel?: string | null
) {
  const normalizedField = field.trim()
  const normalizedLabel = savedLabel?.trim() || ""

  if (
    normalizedLabel &&
    normalizedLabel !== normalizedField &&
    !isDatabaseFieldName(normalizedLabel)
  ) {
    return normalizedLabel
  }

  const mappedLabel = OPERATION_LOG_FIELD_LABELS[normalizedField]
  if (mappedLabel) return mappedLabel
  if (!isDatabaseFieldName(normalizedField)) return normalizedField || "其他信息"
  return "其他信息"
}

export function isOperationLogStructuredValue(value: unknown) {
  return value !== null && typeof value === "object"
}

export function isOperationLogRecord(
  value: unknown
): value is Record<string, unknown> {
  return isOperationLogStructuredValue(value) && !Array.isArray(value)
}

export function areOperationLogValuesEqual(
  before: unknown,
  after: unknown
): boolean {
  if (Object.is(before, after)) return true
  if (Array.isArray(before) || Array.isArray(after)) {
    if (!Array.isArray(before) || !Array.isArray(after)) return false
    return (
      before.length === after.length &&
      before.every((item, index) =>
        areOperationLogValuesEqual(item, after[index])
      )
    )
  }
  if (isOperationLogRecord(before) || isOperationLogRecord(after)) {
    if (!isOperationLogRecord(before) || !isOperationLogRecord(after)) {
      return false
    }
    const keys = new Set([...Object.keys(before), ...Object.keys(after)])
    return Array.from(keys).every((key) =>
      areOperationLogValuesEqual(before[key], after[key])
    )
  }
  return false
}

export function getOperationLogRecordChanges(before: unknown, after: unknown) {
  const beforeRecord = isOperationLogRecord(before) ? before : {}
  const afterRecord = isOperationLogRecord(after) ? after : {}
  const keys = new Set([
    ...Object.keys(beforeRecord),
    ...Object.keys(afterRecord),
  ])

  return Array.from(keys)
    .filter(
      (key) =>
        !areOperationLogValuesEqual(beforeRecord[key], afterRecord[key])
    )
    .map((key) => ({
      key,
      before: beforeRecord[key],
      after: afterRecord[key],
    }))
}

export function formatOperationLogPrimitive(value: unknown) {
  if (value === null || value === undefined || value === "") return "空"
  if (typeof value === "boolean") return value ? "是" : "否"
  return String(value)
}
