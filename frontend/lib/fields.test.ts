import { describe, expect, it } from "vitest"

import { getProductFieldGroups, getProductFieldLabel } from "@/lib/fields"


describe("product archive field groups", () => {
  it("shows the complete style group for C.banner women's products", () => {
    const groups = getProductFieldGroups("cbanner_womens")
    const styleGroup = groups.find((group) => group.label === "女鞋款式信息")

    expect(styleGroup?.fields).toEqual([
      "sole_style",
      "fashion_elements",
      "heel_height",
      "upper_height",
      "opening_depth",
      "boot_shaft",
      "closure_type",
      "mesh_upper_type",
    ])
    expect(getProductFieldLabel("heel_height", "cbanner_womens")).toBe("后跟高")
    expect(getProductFieldLabel("upper_height", "cbanner_womens")).toBe("鞋帮高度")
  })

  it("keeps women's-only fields out of other brand groups", () => {
    const fields = getProductFieldGroups("cbanner_mens").flatMap((group) => group.fields)

    expect(fields).not.toContain("sole_style")
    expect(fields).not.toContain("fashion_elements")
    expect(fields).not.toContain("opening_depth")
    expect(fields).not.toContain("boot_shaft")
    expect(fields).not.toContain("mesh_upper_type")
  })
})
