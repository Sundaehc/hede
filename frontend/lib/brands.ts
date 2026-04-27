export const BRANDS = [
  { key: "all", label: "总览" },
  { key: "qbd_mens", label: "千百度男鞋" },
  { key: "qbd_womens", label: "千百度女鞋" },
  { key: "yandou", label: "烟斗" },
  { key: "yiban", label: "伊伴" },
] as const

export type BrandKey = (typeof BRANDS)[number]["key"]
