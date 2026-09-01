import { describe, expect, it } from "vitest"

import {
  formatOperationLogPrimitive,
  getOperationLogFieldLabel,
  getOperationLogRecordChanges,
} from "@/lib/operation-log-format"

describe("operation log formatting", () => {
  it("translates saved database field names for historical logs", () => {
    expect(getOperationLogFieldLabel("extra_fields", "extra_fields")).toBe(
      "扩展信息"
    )
    expect(getOperationLogFieldLabel("sort_order", "sort_order")).toBe("排序")
    expect(getOperationLogFieldLabel("deleted_at", "deleted_at")).toBe(
      "删除时间"
    )
  })

  it("translates nested extension fields", () => {
    expect(getOperationLogFieldLabel("delivery_date")).toBe("到货日期")
    expect(getOperationLogFieldLabel("size_labels")).toBe("尺码列表")
    expect(getOperationLogFieldLabel("inner_color_code")).toBe(
      "色号（鞋内丝印）"
    )
    expect(getOperationLogFieldLabel("size_name")).toBe("尺码")
    expect(getOperationLogFieldLabel("barcode")).toBe("条码")
  })

  it("keeps an existing Chinese business label", () => {
    expect(getOperationLogFieldLabel("name", "供应商名称")).toBe("供应商名称")
  })

  it("does not expose an unknown database field name", () => {
    expect(getOperationLogFieldLabel("unknown_field", "unknown_field")).toBe(
      "其他信息"
    )
  })

  it("formats primitive values for Chinese logs", () => {
    expect(formatOperationLogPrimitive(true)).toBe("是")
    expect(formatOperationLogPrimitive(false)).toBe("否")
    expect(formatOperationLogPrimitive(null)).toBe("空")
  })

  it("keeps only changed nested fields", () => {
    expect(
      getOperationLogRecordChanges(
        {
          delivery_date: "2026-08-31",
          size_range: "34-40",
          factory_code: "A01",
        },
        {
          delivery_date: "2026-09-12",
          size_range: "34-40",
          factory_code: "A01",
        }
      )
    ).toEqual([
      {
        key: "delivery_date",
        before: "2026-08-31",
        after: "2026-09-12",
      },
    ])
  })
})
