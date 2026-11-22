import { describe, expect, it } from "vitest"

import {
  formatOperationLogPrimitive,
  formatOperationLogSummary,
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
    expect(getOperationLogFieldLabel("cost_manual_override", "cost_manual_override")).toBe(
      "工厂出货价手动维护标记"
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

  it("localizes historical field lists while preserving the product name, values and sync result", () => {
    const changes = [
      { field: "cost", label: "工厂出货价", before: "100", after: "120" },
      { field: "cost_manual_override", label: "cost_manual_override", before: false, after: true },
      { field: "remark", label: "备注", before: "", after: "cost_manual_override" },
    ]
    const summary = "编辑商品 cost_manual_override：修改了 工厂出货价、cost_manual_override、备注；同步更新 1 条关联单据明细（1 张单据）"
    expect(formatOperationLogSummary(summary, changes)).toBe(
      "编辑商品 cost_manual_override：修改了 工厂出货价、工厂出货价手动维护标记、备注；同步更新 1 条关联单据明细（1 张单据）"
    )
    expect(changes[2].after).toBe("cost_manual_override")
    expect(changes[1].label).toBe("cost_manual_override")
    expect(formatOperationLogSummary("备注 cost_manual_override", changes)).toBe("备注 cost_manual_override")
    expect(formatOperationLogSummary(summary, null)).toBe(summary)
  })

  it("keeps the field count suffix and displays unmapped technical fields in Chinese", () => {
    const changes = Array.from({ length: 9 }, (_, index) => ({ field: `unknown_field_${index}`, label: `unknown_field_${index}`, before: 0, after: 1 }))
    const summary = `编辑商品 SKU001：修改了 ${changes.slice(0, 8).map((change) => change.label).join("、")}等字段；同步更新 2 条关联单据明细（1 张单据）`
    const result = formatOperationLogSummary(summary, changes)
    expect(result).not.toContain("unknown_field")
    expect(result).toContain("其他信息")
    expect(result).toContain("等字段；同步更新 2 条关联单据明细（1 张单据）")
    expect(getOperationLogFieldLabel("unknownField", "unknownField")).toBe("其他信息")
  })
})
