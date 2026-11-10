"""Compare warehouse detail queries using isolated, deterministic synthetic data."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import event
from domain.inventory_schema import (
    GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE,
    INVENTORY_DETAIL_TABLE, INVENTORY_TABLE,
)
import storage.inventory_repository as repository_module
from verify_warehouse_inventory_summary import WarehouseSummaryTests

namespace = dict(vars(repository_module))
baseline_path = Path(__file__).with_name("warehouse_detail_baseline_20261110.py")
exec(compile(baseline_path.read_text(encoding="utf-8"), str(baseline_path), "exec"), namespace)
baseline = namespace["get_warehouse_inventory"]


class WarehouseDetailOptimizationTests(WarehouseSummaryTests):
    def populate(self):
        rng = random.Random(20261110)
        with self.engine.begin() as connection:
            connection.execute(GENERAL_CUSTOMER_SHOP_TABLE.insert(), {
                "id": 1, "customer_name": "甲", "shop_name": "甲-内销客户",
            })
            connection.execute(GENERAL_CUSTOMER_UNIT_TABLE.insert(), {
                "id": 1, "shop_id": 1, "unit_name": "内销单位",
            })
        for index in range(300):
            day = rng.choice(("2026-09-30", "2026-10-01", "2026-10-15", "2026-10-31", "2026-11-01", None))
            self.movement(
                rng.choice(("进货单", "批发销售单", "同价调拨单", "报溢单", "报损单", "进货退货单", "批发销售退货单", "进货订单", "应付款增加")),
                rng.choice((None, 0, -3, 7, "1.125", "-.25")), day=day,
                warehouse=rng.choice(("A", "B", "历史仓库", "", None)),
                supplier=rng.choice(("A", "B", "供应商", "甲-内销客户", "内销单位", " 总部 采购 ", None)),
                legacy=index % 3 == 0, deleted=index % 11 == 0,
                unit_price=rng.choice((None, 0, 1, 2)),
            )
            with self.engine.begin() as connection:
                # Deliberately disagree with the document quantity/date text.
                values = {"total_count": "999999"}
                if day and index % 13 == 0:
                    values["date_value"] = date(2026, 10, 15)
                connection.execute(INVENTORY_TABLE.update().where(INVENTORY_TABLE.c.id == self.next_id).values(**values))
                connection.execute(INVENTORY_DETAIL_TABLE.update().where(INVENTORY_DETAIL_TABLE.c.id == self.next_id).values(
                    product_code=rng.choice((None, "", "P0", "P1", "P1-extra", "前导零001")),
                    product_name=rng.choice((None, "", "鞋", "另一个名称")),
                    color_name=rng.choice((None, "", "黑色")), color_spec=rng.choice((None, "", "规格")),
                ))
                for line in range(index % 4):
                    connection.execute(INVENTORY_DETAIL_TABLE.insert(), {
                        "id": 10000 + index * 4 + line, "document_id": self.next_id,
                        "product_code": rng.choice(("P0", "P1", "HIDDEN")),
                        "product_name": "鞋", "color_name": None, "color_spec": "",
                        "quantity": rng.choice((None, Decimal(".125"), Decimal("-1.25"), Decimal("4"))),
                        "unit_price": rng.choice((None, 0, 1)), "amount": rng.choice((None, 0, 2)),
                    })

    def test_baseline_matches_across_filters_pages_and_date_ranges(self):
        self.populate()
        ranges = ((None, None), ("2026-10-01", "2026-10-31"), (None, "2026-10-31"),
                  ("2026-10-15", None), ("2026-10-15", "2026-10-15"), ("2026-12-01", "2026-12-31"),
                  ("legacy-start", "legacy-end"))
        comparisons = 0
        for warehouse in ("A", "B", "空仓", "历史仓库", "", None):
            for start, end in ranges:
                for search in (None, "P1", "  P0  ", "不存在"):
                    for ending in (False, True):
                        for page in (1, 2, 999):
                            params = dict(warehouse_name=warehouse, date_start=start, date_end=end,
                                          product_code=search, ending_nonzero=ending, page=page, page_size=3)
                            with self.subTest(**params):
                                self.assertEqual(self.repo.get_warehouse_inventory(**params), baseline(self.repo, **params))
                            comparisons += 1
        print(f"Baseline comparisons: {comparisons}", flush=True)

    def test_inventory_executes_one_statement_and_reflects_source_changes(self):
        self.movement("进货单", "1.125")
        params = dict(warehouse_name="A", page=1, page_size=20)
        statements = []
        listener = lambda conn, cursor, stmt, params, context, many: statements.append(stmt)
        event.listen(self.engine, "before_cursor_execute", listener)
        try:
            self.assertEqual(self.repo.get_warehouse_inventory(**params)["totals"]["ending_qty"], "1.125")
        finally:
            event.remove(self.engine, "before_cursor_execute", listener)
        self.assertEqual(len(statements), 1)
        with self.engine.begin() as connection:
            connection.execute(INVENTORY_DETAIL_TABLE.update().values(quantity=Decimal("2.25")))
        self.assertEqual(self.repo.get_warehouse_inventory(**params)["totals"]["ending_qty"], "2.25")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WarehouseDetailOptimizationTests)
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
