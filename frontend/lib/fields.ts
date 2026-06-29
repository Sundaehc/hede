export const SEASON_OPTIONS = ["春季", "夏季", "秋季", "冬季", "春夏", "春秋", "秋冬"] as const

export const FIELD_LABELS: Record<string, string> = {
  image_path: "图片路径",
  sku: "商品货号",
  original_sku: "原始货号",
  group_name: "组别",
  product_level: "商品等级",
  cost: "成本",
  factory_sku: "工厂货号",
  color: "颜色",
  season_category: "季节分类",
  year: "年份",
  upper_material: "鞋面材质",
  lining_material: "内里材质",
  outsole_material: "大底材质",
  insole_material: "鞋垫材质",
  execution_standard: "执行标准",
  heel_height: "跟高",
  shoe_width: "鞋宽",
  shoe_length: "鞋长",
  shaft_circumference: "筒围",
  shaft_height: "筒高",
  internal_height_increase: "内增高",
  internal_height_note: "内增高备注",
  upper_height: "鞋帮",
  toe_shape: "鞋头款式",
  closure_type: "闭合方式",
  shoe_box_spec: "鞋盒规格",
  first_order_time: "首单时间",
  size_range: "尺码段",
  product_model: "产品型号",
  supplier_name: "供应商名",
  color_code: "颜色代码",
  launch_date: "上市时间",
}

export const FIELD_GROUPS = [
  {
    label: "基础信息",
    fields: ["original_sku", "sku", "group_name", "product_level", "factory_sku", "cost", "color", "color_code", "season_category", "year"],
  },
  {
    label: "材质信息",
    fields: ["upper_material", "lining_material", "outsole_material", "insole_material"],
  },
  {
    label: "尺寸信息",
    fields: [
      "heel_height",
      "shoe_width",
      "shoe_length",
      "shaft_circumference",
      "shaft_height",
      "internal_height_increase",
      "internal_height_note",
      "upper_height",
    ],
  },
  {
    label: "其他",
    fields: ["toe_shape", "closure_type", "shoe_box_spec", "execution_standard", "first_order_time", "size_range", "product_model", "supplier_name", "launch_date"],
  },
] as const

export const CARD_DISPLAY_FIELDS = FIELD_GROUPS.flatMap((g) => g.fields)

export const ALL_PRODUCT_FIELDS = FIELD_GROUPS.flatMap((g) => g.fields)
