import argparse
import cProfile
from datetime import datetime
import io
import json
from pathlib import Path
import pstats
import sys
from time import perf_counter
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.encoders import jsonable_encoder
from sqlalchemy import create_engine, event

from api.fine_table_cache import clear_fine_table_cache
from api.product_goods_cache import clear_product_goods_cache
from api.routes.fine_table import list_fine_table
from api.routes.product_goods import list_product_goods
from config import load_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--case", action="append")
    parser.add_argument("--warm-pages", action="store_true")
    args = parser.parse_args()
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, connect_args={
        "options": "-c default_transaction_read_only=on -c statement_timeout=45000 -c lock_timeout=3000",
    })
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=settings, repository=SimpleNamespace(engine=engine),
    )))
    queries = []

    def before_query(connection, cursor, statement, parameters, context, executemany):
        context.profile_started_at = perf_counter()

    def after_query(connection, cursor, statement, parameters, context, executemany):
        queries.append({"sql": statement, "parameters": parameters,
                        "elapsed_ms": round((perf_counter() - context.profile_started_at) * 1000, 3)})

    event.listen(engine, "before_cursor_execute", before_query)
    event.listen(engine, "after_cursor_execute", after_query)
    results = []
    cases = [("goods-womens-1", "goods", "cbanner_womens", 1),
             ("goods-womens-2", "goods", "cbanner_womens", 2),
             ("goods-mens-1", "goods", "cbanner_mens", 1),
             ("fine-mens-1", "fine", "cbanner_mens", 1),
             ("fine-mens-2", "fine", "cbanner_mens", 2),
             ("fine-womens-1", "fine", "cbanner_womens", 1)]
    try:
        for name, endpoint, brand, page in cases:
            if args.case and name not in args.case:
                continue
            if not args.warm_pages or not results:
                clear_product_goods_cache()
                clear_fine_table_cache()
            queries.clear()
            profiler = cProfile.Profile()
            started_at = perf_counter()
            print(f"[PROFILE] {name}", flush=True)
            profiler.enable()
            if endpoint == "goods":
                payload = list_product_goods(request, brand=brand, view="goods", query=None,
                    platform=None, year=None, filters=None, snapshot_date=None, cache_bust=None,
                    page=page, page_size=50)
            else:
                payload = list_fine_table(request, brand=brand, query=None, sku_prefix=None,
                    season=None, filters=None, cache_bust=None, include_all=False, page=page, page_size=50)
            profiler.disable()
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            profile_output = io.StringIO()
            pstats.Stats(profiler, stream=profile_output).sort_stats("cumulative").print_stats(35)
            profile_path = ROOT / f"outputs/product-pagination-{args.label}-{name}-20261014.txt"
            profile_path.write_text(profile_output.getvalue(), encoding="utf-8")
            result = {"case": name, "elapsed_ms": elapsed_ms, "total": payload["total"],
                      "item_count": len(payload["items"]), "query_count": len(queries),
                      "queries": list(queries), "payload": jsonable_encoder(payload)}
            results.append(result)
            (ROOT / f"outputs/product-pagination-{args.label}-20261014.json").write_text(
                json.dumps({"generated_at": datetime.now().astimezone().isoformat(), "cases": results},
                           ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(f"[RESULT] {name}: {elapsed_ms} ms, queries={len(queries)}, total={payload['total']}", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
