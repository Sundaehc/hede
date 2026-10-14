import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Text, create_engine, literal, select
from api.fine_table_cache import clear_fine_table_cache
from api.product_goods_cache import clear_product_goods_cache
from api.routes import fine_table, product_goods
from config import load_settings
from domain import excluded_skus


def original_module(path, name):
    source = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True,
                            check=True, encoding="utf-8").stdout
    module = ModuleType(name)
    module.__file__ = str(ROOT / path)
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def main():
    original_excluded = original_module("backend/domain/excluded_skus.py", "original_excluded")
    original_fine = original_module("backend/api/routes/fine_table.py", "original_fine")
    original_goods = original_module("backend/api/routes/product_goods.py", "original_goods")
    original_fine.not_excluded_sku_condition = original_excluded.not_excluded_sku_condition
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, connect_args={
        "options": "-c default_transaction_read_only=on -c statement_timeout=45000 -c lock_timeout=3000",
    })
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=settings, repository=SimpleNamespace(engine=engine),
    )))
    report = []
    try:
        baseline = json.loads((ROOT / "outputs/product-pagination-before-20261014.json").read_text(encoding="utf-8"))
        goods_code = baseline["cases"][0]["payload"]["items"][0]["goods_code"]
        fine_code = next(item for item in baseline["cases"] if item["case"] == "fine-mens-1")["payload"]["items"][0]["sku"]
        goods_defaults = {"brand": "cbanner_womens", "view": "goods", "query": None, "platform": None,
                          "year": None, "filters": None, "snapshot_date": None, "cache_bust": "verify", "page": 1, "page_size": 5}
        fine_defaults = {"brand": "cbanner_mens", "query": None, "sku_prefix": None, "season": None,
                         "filters": None, "cache_bust": "verify", "include_all": False, "page": 1, "page_size": 5}
        scenarios = [
            ("goods-search", original_goods.list_product_goods, product_goods.list_product_goods, {**goods_defaults, "query": goods_code}),
            ("goods-style", original_goods.list_product_goods, product_goods.list_product_goods, {**goods_defaults, "view": "style_summary", "query": goods_code}),
            ("goods-year", original_goods.list_product_goods, product_goods.list_product_goods, {**goods_defaults, "year": "2026", "page": 2}),
            ("fine-search", original_fine.list_fine_table, fine_table.list_fine_table, {**fine_defaults, "query": fine_code}),
            ("fine-prefix", original_fine.list_fine_table, fine_table.list_fine_table, {**fine_defaults, "sku_prefix": fine_code[:5], "page": 2}),
            ("fine-payload-filter", original_fine.list_fine_table, fine_table.list_fine_table, {**fine_defaults, "query": fine_code, "filters": '[{"field":"stock_qty","operator":"not_in","values":["999999"]}]'}),
            ("fine-export", original_fine.list_fine_table, fine_table.list_fine_table, {**fine_defaults, "query": fine_code, "include_all": True}),
        ]
        for name, old_function, new_function, parameters in scenarios:
            print(f"[VERIFY] {name}", flush=True)
            clear_product_goods_cache()
            clear_fine_table_cache()
            old_payload = jsonable_encoder(old_function(request, **parameters))
            clear_product_goods_cache()
            clear_fine_table_cache()
            new_payload = jsonable_encoder(new_function(request, **parameters))
            if old_payload != new_payload:
                raise AssertionError(f"Payload differs: {name}")
            report.append({"case": name, "result_equal": True, "total": new_payload["total"], "item_count": len(new_payload["items"])})
        values = frozenset({'A"B', 'A\\B', 'A,B', '中文', 'NULL'})
        previous_values = excluded_skus.EXCLUDED_SKUS
        excluded_skus.EXCLUDED_SKUS = values
        original_excluded.EXCLUDED_SKUS = values
        try:
            with engine.connect() as connection:
                for value in [None, "", *values, "OTHER"]:
                    expression = literal(value, type_=Text())
                    original = connection.execute(select(original_excluded.not_excluded_sku_condition(expression))).scalar_one()
                    optimized = connection.execute(select(excluded_skus.not_excluded_sku_condition(expression))).scalar_one()
                    if original != optimized:
                        raise AssertionError("Excluded SKU behavior differs")
        finally:
            excluded_skus.EXCLUDED_SKUS = previous_values
        report.append({"case": "excluded-sku-escaping-and-null", "result_equal": True})
        (ROOT / "outputs/product-pagination-results-verified-20261014.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
