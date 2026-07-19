from __future__ import annotations

from sqlalchemy import create_engine, select

from api.routes.product_goods import _sales_matrix_payload
from config import load_settings
from domain.schema import PRODUCT_TABLES


def main() -> None:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as connection:
        for brand, product_table in PRODUCT_TABLES.items():
            rows = [
                dict(row)
                for row in connection.execute(
                    select(product_table.c.sku, product_table.c.original_sku)
                    .where(product_table.c.sku.isnot(None))
                    .order_by(product_table.c.year.desc().nulls_last(), product_table.c.sku)
                    .limit(50)
                ).mappings()
            ]
            product_sales_codes = {
                str(row["sku"] or "").strip(): str(row["original_sku"] or "").strip()
                for row in rows
                if str(row["sku"] or "").strip()
            }
            _, _, _, _, summary = _sales_matrix_payload(
                connection,
                engine,
                product_sales_codes,
                brand=brand,
            )
            with_sales = [
                (sku, values["total_sales"])
                for sku, values in summary.items()
                if int(values["total_sales"] or 0) > 0
            ]
            print(f"{brand}: rows={len(rows)}, with_sales={len(with_sales)}, examples={with_sales[:3]}")


if __name__ == "__main__":
    main()
