import { afterEach, expect, test, vi } from "vitest"
import { listSuppliers, listSuppliersByBrand, type SupplierItem } from "./api"

afterEach(() => vi.restoreAllMocks())

function supplier(id: number, brand: string, name: string): SupplierItem {
  return {
    id,
    brand,
    name,
    factory_code: `FACTORY-${id}`,
    contact: null,
    wechat: null,
    cooperation_status: "合作中",
    address: null,
    notes: null,
  }
}

function response(items: SupplierItem[]) {
  return new Response(
    JSON.stringify({
      items,
      total: items.length,
      page: 1,
      page_size: items.length,
    }),
    {
      headers: { "Content-Type": "application/json" },
    }
  )
}

test("Eblan product options include both supplier groups with their original identities", async () => {
  const mens = supplier(1, "eblan", "乙厂（伊伴）")
  const womens = supplier(2, "eblan_womens", "甲厂（伊伴女鞋）")
  const fetchMock = vi
    .spyOn(global, "fetch")
    .mockImplementation(async (input) => {
      const brand = new URL(String(input), "http://localhost").searchParams.get(
        "brand"
      )
      return response(brand === "eblan" ? [mens] : [womens])
    })
  const result = await listSuppliersByBrand("eblan")
  expect(
    fetchMock.mock.calls.map(([input]) =>
      new URL(String(input), "http://localhost").searchParams.get("brand")
    )
  ).toEqual(["eblan", "eblan_womens"])
  expect(result.items).toEqual([womens, mens])
  expect(result).toMatchObject({ total: 2, page: 1, page_size: 2 })
  expect(
    fetchMock.mock.calls.every(([, options]) => options?.cache === "no-store")
  ).toBe(true)
})

test("same-name suppliers in separate management groups retain separate records", async () => {
  vi.spyOn(global, "fetch")
    .mockResolvedValueOnce(response([supplier(1, "eblan", "同名工厂")]))
    .mockResolvedValueOnce(response([supplier(2, "eblan_womens", "同名工厂")]))
  const result = await listSuppliersByBrand("eblan")
  expect(result.items.map((item) => item.id)).toEqual([1, 2])
  expect(result.total).toBe(2)
})

test.each(["cbanner_mens", "cbanner_womens", "smiley", "ni", "custom"])(
  "keeps product supplier options isolated for %s",
  async (brand) => {
    const item = supplier(3, brand, "测试工厂")
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(response([item]))
    expect((await listSuppliersByBrand(brand)).items).toEqual([item])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(
      new URL(
        String(fetchMock.mock.calls[0][0]),
        "http://localhost"
      ).searchParams.get("brand")
    ).toBe(brand)
  }
)

test("a failed supplier group does not silently produce an incomplete Eblan list", async () => {
  vi.spyOn(global, "fetch")
    .mockResolvedValueOnce(response([supplier(1, "eblan", "男鞋工厂")]))
    .mockRejectedValueOnce(new Error("女鞋供应商读取失败"))
  await expect(listSuppliersByBrand("eblan")).rejects.toThrow(
    "女鞋供应商读取失败"
  )
})

test("supplier management continues to query the selected management group only", async () => {
  const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(response([]))
  await listSuppliers({ brand: "eblan" })
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(
    new URL(
      String(fetchMock.mock.calls[0][0]),
      "http://localhost"
    ).searchParams.get("brand")
  ).toBe("eblan")
})
