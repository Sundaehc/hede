"""Move legacy product_goods_historical_sales rows into annual tables."""
from __future__ import annotations

import argparse

from sqlalchemy import create_engine, inspect, text

from config import load_settings
from domain.product_goods_historical_sales_schema import HISTORICAL_SALES_YEARS, ensure_product_goods_historical_sales_table


LEGACY_TABLE = "product_goods_historical_sales"
COLUMNS = (
    "brand", "sales_year", "sales_date", "channel", "style_code", "product_code", "original_sku", "size", "color",
    "sales_quantity", "sales_amount", "source_workbook", "source_sheet", "source_row_number", "created_at",
)


def _summary(connection, table_name: str, sales_year: int) -> tuple[int, int]:
    row = connection.execute(
        text(f"SELECT COUNT(*), COALESCE(SUM(sales_quantity), 0) FROM {table_name} WHERE sales_year = :sales_year"),
        {"sales_year": sales_year},
    ).one()
    return int(row[0]), int(row[1])


def migrate(*, drop_legacy: bool = False) -> dict[int, tuple[int, int]]:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    inspector = inspect(engine)
    if not inspector.has_table(LEGACY_TABLE):
        raise RuntimeError(f"未找到旧表: {LEGACY_TABLE}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE product_goods_historical_sales
                SET brand = 'cbanner_womens'
                WHERE brand IS NULL
                  AND source_workbook = '赫德货品表（千百度）7.15.xlsx'
                """
            )
        )
    results: dict[int, tuple[int, int]] = {}
    column_list = ", ".join(COLUMNS)
    for sales_year in HISTORICAL_SALES_YEARS:
        target = ensure_product_goods_historical_sales_table(engine, sales_year)
        with engine.begin() as connection:
            source_count, source_quantity = _summary(connection, LEGACY_TABLE, sales_year)
            connection.execute(
                text(
                    f"""
                    INSERT INTO {target.name} ({column_list})
                    SELECT {column_list}
                    FROM {LEGACY_TABLE}
                    WHERE sales_year = :sales_year
                    ON CONFLICT (source_workbook, source_sheet, source_row_number) DO NOTHING
                    """
                ),
                {"sales_year": sales_year},
            )
            target_count, target_quantity = _summary(connection, target.name, sales_year)
            if (target_count, target_quantity) != (source_count, source_quantity):
                raise RuntimeError(
                    f"{sales_year} 年迁移校验失败: 旧表 {(source_count, source_quantity)}，新表 {(target_count, target_quantity)}"
                )
            results[sales_year] = (target_count, target_quantity)
    if drop_legacy:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE {LEGACY_TABLE}"))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate product-goods historical sales to annual tables")
    parser.add_argument("--drop-legacy", action="store_true", help="仅在年度表校验通过后删除旧单表")
    args = parser.parse_args()
    print(migrate(drop_legacy=args.drop_legacy))


if __name__ == "__main__":
    main()
