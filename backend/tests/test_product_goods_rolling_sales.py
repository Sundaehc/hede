from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text

from api.routes.product_goods import _sales_matrix_payload


def _create_daily_sales(connection, year: int) -> None:
    connection.execute(text(f"""
        CREATE TABLE jst_daily_sales_{year} (
            sales_date DATE, product_code TEXT, style_code TEXT, channel TEXT,
            color_spec TEXT, net_sales_quantity INTEGER, sales_order_count INTEGER,
            return_quantity INTEGER
        )
    """))


def _add_daily_sale(connection, year: int, day: date, quantity: int) -> None:
    connection.execute(
        text(f"""
            INSERT INTO jst_daily_sales_{year}
                (sales_date, product_code, style_code, channel, color_spec, net_sales_quantity)
            VALUES (:day, 'SKU-1', 'STYLE-1', '天猫', '36', :quantity)
        """),
        {"day": day, "quantity": quantity},
    )


def test_month_sales_uses_inclusive_rolling_30_days_across_months(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sales.db'}")
    try:
        with engine.begin() as connection:
            _create_daily_sales(connection, 2026)
            for day, quantity in (
                (date(2026, 2, 1), 100),
                (date(2026, 2, 2), 2),
                (date(2026, 3, 3), 3),
                (date(2026, 3, 4), 100),
            ):
                _add_daily_sale(connection, 2026, day, quantity)
            _, _, platforms, _, summaries = _sales_matrix_payload(
                connection, engine, {"SKU-1": "STYLE-1"}, brand="cbanner_womens", as_of_date=date(2026, 3, 3)
            )

        assert summaries["SKU-1"]["month_sales"] == 5
        assert platforms["SKU-1"]["monthly"]["天猫"] == 5
    finally:
        engine.dispose()


def test_month_sales_includes_previous_year_historical_sales_without_daily_duplication(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sales.db'}")
    try:
        with engine.begin() as connection:
            _create_daily_sales(connection, 2025)
            _create_daily_sales(connection, 2026)
            connection.execute(text("""
                CREATE TABLE product_goods_historical_sales_2025 (
                    brand TEXT, product_code TEXT, original_sku TEXT, sales_date DATE,
                    channel TEXT, size TEXT, sales_quantity INTEGER
                )
            """))
            for day, quantity in ((date(2025, 12, 6), 100), (date(2025, 12, 7), 4)):
                connection.execute(
                    text("""
                        INSERT INTO product_goods_historical_sales_2025
                            (brand, product_code, original_sku, sales_date, channel, size, sales_quantity)
                        VALUES ('cbanner_womens', 'SKU-1', 'STYLE-1', :day, '天猫', '36', :quantity)
                    """),
                    {"day": day, "quantity": quantity},
                )
            _add_daily_sale(connection, 2025, date(2025, 12, 7), 4)
            _add_daily_sale(connection, 2026, date(2026, 1, 5), 3)
            _, _, platforms, _, summaries = _sales_matrix_payload(
                connection, engine, {"SKU-1": "STYLE-1"}, brand="cbanner_womens", as_of_date=date(2026, 1, 5)
            )

        assert summaries["SKU-1"]["month_sales"] == 7
        assert platforms["SKU-1"]["monthly"]["天猫"] == 7
    finally:
        engine.dispose()


def test_month_sales_includes_previous_year_daily_sales_when_no_historical_table(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sales.db'}")
    try:
        with engine.begin() as connection:
            _create_daily_sales(connection, 2025)
            _create_daily_sales(connection, 2026)
            _add_daily_sale(connection, 2025, date(2025, 12, 7), 4)
            _add_daily_sale(connection, 2026, date(2026, 1, 5), 3)
            _, _, platforms, _, summaries = _sales_matrix_payload(
                connection, engine, {"SKU-1": "STYLE-1"}, brand="cbanner_womens", as_of_date=date(2026, 1, 5)
            )

        assert summaries["SKU-1"]["month_sales"] == 7
        assert platforms["SKU-1"]["monthly"]["天猫"] == 7
    finally:
        engine.dispose()


def test_month_sales_uses_historical_sales_without_daily_table(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sales.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE product_goods_historical_sales_2025 (
                    brand TEXT, product_code TEXT, original_sku TEXT, sales_date DATE,
                    channel TEXT, size TEXT, sales_quantity INTEGER
                )
            """))
            for day, quantity in ((date(2025, 2, 1), 100), (date(2025, 2, 2), 2), (date(2025, 3, 3), 3), (date(2025, 3, 4), 100)):
                connection.execute(
                    text("""
                        INSERT INTO product_goods_historical_sales_2025
                            (brand, product_code, original_sku, sales_date, channel, size, sales_quantity)
                        VALUES ('cbanner_womens', 'SKU-1', 'STYLE-1', :day, '天猫', '36', :quantity)
                    """),
                    {"day": day, "quantity": quantity},
                )
            _, _, platforms, _, summaries = _sales_matrix_payload(
                connection, engine, {"SKU-1": "STYLE-1"}, brand="cbanner_womens", as_of_date=date(2025, 3, 3)
            )

        assert summaries["SKU-1"]["month_sales"] == 5
        assert platforms["SKU-1"]["monthly"]["天猫"] == 5
    finally:
        engine.dispose()
