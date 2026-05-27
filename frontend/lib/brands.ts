export const BRANDS = [
  { key: "all", label: "总览" },
  { key: "cbanner_mens", label: "千百度男鞋" },
  { key: "cbanner_womens", label: "千百度女鞋" },
  { key: "yandou", label: "烟斗" },
  { key: "eblan", label: "伊伴" },
] as const

export type BrandKey = (typeof BRANDS)[number]["key"]
