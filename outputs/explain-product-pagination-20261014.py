import json
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, text
from config import load_settings

engine = create_engine(load_settings(require_database=True).database_url, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=3000",
})
parser = argparse.ArgumentParser()
parser.add_argument("--label", default="before")
args = parser.parse_args()
report = json.loads((ROOT / f"outputs/product-pagination-{args.label}-20261014.json").read_text(encoding="utf-8"))
lines = []
with engine.connect() as connection:
    indexes = connection.execute(text("""
        SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='public'
        AND (tablename IN ('gj_merged_product_info', 'cbanner_mens_products', 'cbanner_womens_products',
            'vip_product_daily_snapshots', 'product_goods_sales_periods', 'vip_daily_sales_2026')
            OR tablename LIKE 'jst_aftersale_returns%') ORDER BY tablename, indexname
    """)).mappings().all()
    (ROOT / f"outputs/product-pagination-indexes-{args.label}-20261014.json").write_text(
        json.dumps([dict(row) for row in indexes], ensure_ascii=False, indent=2), encoding="utf-8")
    for case_name in ("goods-womens-1", "fine-mens-2"):
        case = next(item for item in report["cases"] if item["case"] == case_name)
        for query in sorted(case["queries"], key=lambda item: item["elapsed_ms"], reverse=True)[:5]:
            lines.append(f"=== {case_name}: {query['sql']} ===")
            print(f"[PLAN] {case_name} {query['elapsed_ms']} ms", flush=True)
            lines.extend(connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, TIMING OFF) " + query["sql"], query["parameters"],
            ).scalars().all())
engine.dispose()
(ROOT / f"outputs/product-pagination-{args.label}-plans-20261014.txt").write_text("\n".join(lines), encoding="utf-8")
