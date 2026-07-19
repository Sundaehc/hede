"""Count product-goods records that have matched sales data."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import create_engine, select

from config import load_settings
from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from domain.product_goods_historical_sales_schema import HISTORICAL_SALES_YEARS, product_goods_historical_sales_table_for_year
from domain.product_goods_sales_period_schema import PRODUCT_GOODS_SALES_PERIODS_TABLE
from domain.schema import PRODUCT_TABLES


def _prefix_index(codes: set[str]) -> dict[str, object]:
    root: dict[str, object] = {}
    for code in codes:
        node = root
        for character in code:
            node = node.setdefault(character, {})  # type: ignore[assignment]
        node["\0"] = code
    return root


def _longest_prefix(code: object, index: dict[str, object]) -> str | None:
    node = index
    matched: str | None = None
    for character in str(code or "").strip():
        child = node.get(character)
        if not isinstance(child, dict):
            break
        node = child
        candidate = node.get("\0")
        if isinstance(candidate, str):
            matched = candidate
    return matched


def main() -> None:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as connection:
        for brand, product_table in PRODUCT_TABLES.items():
            products = {
                str(row["sku"] or "").strip(): str(row["original_sku"] or "").strip()
                for row in connection.execute(select(product_table.c.sku, product_table.c.original_sku)).mappings()
                if str(row["sku"] or "").strip()
            }
            code_index = _prefix_index(set(products))
            style_matches: dict[str, list[str]] = defaultdict(list)
            for sku, style_code in products.items():
                if style_code:
                    style_matches[style_code].append(sku)
            unique_styles = {style_code: skus[0] for style_code, skus in style_matches.items() if len(skus) == 1}
            matched: set[str] = set()

            def add(code: object, style_code: object, quantity: object) -> None:
                if int(quantity or 0) == 0:
                    return
                sku = _longest_prefix(code, code_index) or unique_styles.get(str(style_code or "").strip())
                if sku:
                    matched.add(sku)

            for sales_year in HISTORICAL_SALES_YEARS:
                table = product_goods_historical_sales_table_for_year(sales_year)
                for row in connection.execution_options(stream_results=True).execute(
                    select(table.c.product_code, table.c.original_sku, table.c.sales_quantity).where(table.c.brand == brand)
                ).mappings():
                    add(row["product_code"], row["original_sku"], row["sales_quantity"])

            for table in (jst_daily_sales_table_for_year(2026), vip_daily_sales_table_for_year(2026)):
                if not engine.dialect.has_table(connection, table.name):
                    continue
                code_column = table.c.product_code if "product_code" in table.c else table.c.goods_code
                style_column = table.c.style_code
                quantity_column = table.c.net_sales_quantity if "net_sales_quantity" in table.c else table.c.sales_quantity
                for row in connection.execution_options(stream_results=True).execute(
                    select(code_column, style_column, quantity_column)
                ).mappings():
                    add(row[code_column.name], row[style_column.name], row[quantity_column.name])

            if engine.dialect.has_table(connection, PRODUCT_GOODS_SALES_PERIODS_TABLE.name):
                for row in connection.execution_options(stream_results=True).execute(
                    select(
                        PRODUCT_GOODS_SALES_PERIODS_TABLE.c.product_code,
                        PRODUCT_GOODS_SALES_PERIODS_TABLE.c.style_code,
                        PRODUCT_GOODS_SALES_PERIODS_TABLE.c.sales_quantity,
                    ).where(PRODUCT_GOODS_SALES_PERIODS_TABLE.c.brand == brand)
                ).mappings():
                    add(row["product_code"], row["style_code"], row["sales_quantity"])

            print(f"{brand}: total={len(products)}, with_sales={len(matched)}, without_sales={len(products) - len(matched)}")


if __name__ == "__main__":
    main()
