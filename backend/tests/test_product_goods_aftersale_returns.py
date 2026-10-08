from datetime import date, timedelta

from sqlalchemy import create_engine, text

from api.routes.product_goods import _aftersale_return_quantities, _style_summary_item


def test_aftersale_returns_use_business_date_and_longest_goods_code(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'returns.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE jst_aftersale_returns (
                    original_goods_code TEXT, returned_qty INTEGER,
                    application_date_value DATE, order_date_value DATE, order_time_value DATE
                )
            """))
            records = [
                ("SKU-1-36", 2, "2026-10-07", "2026-09-30", None),
                ("SKU-1-37", 3, None, "2026-10-08", None),
                ("SKU-12-38", 4, None, None, "2026-10-06"),
                ("SKU-1-39", 5, "2026-10-09", "2026-10-01", None),
                ("SKU-1-40", 6, None, None, None),
                ("OTHER", 7, "2026-10-07", None, None),
            ]
            for code, quantity, application, order, order_time in records:
                connection.execute(
                    text("""
                        INSERT INTO jst_aftersale_returns
                            (original_goods_code, returned_qty, application_date_value, order_date_value, order_time_value)
                        VALUES (:code, :quantity, :application, :order, :order_time)
                    """),
                    {"code": code, "quantity": quantity, "application": application, "order": order, "order_time": order_time},
                )

            codes = ["SKU-1", "SKU-12", "SKU-2"]
            assert _aftersale_return_quantities(connection, codes, as_of_date=date(2026, 10, 7)) == {
                "SKU-1": 2,
                "SKU-12": 4,
            }
            assert _aftersale_return_quantities(connection, codes, as_of_date=date(2026, 10, 8)) == {
                "SKU-1": 5,
                "SKU-12": 4,
            }
    finally:
        engine.dispose()


def test_current_aftersale_returns_exclude_future_records(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'returns.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE jst_aftersale_returns (
                    original_goods_code TEXT, returned_qty INTEGER,
                    application_date_value DATE, order_date_value DATE, order_time_value DATE
                )
            """))
            connection.execute(
                text("""
                    INSERT INTO jst_aftersale_returns (original_goods_code, returned_qty, application_date_value)
                    VALUES ('SKU-1', 2, :today), ('SKU-1', 10, :tomorrow)
                """),
                {"today": date.today(), "tomorrow": date.today() + timedelta(days=1)},
            )
            assert _aftersale_return_quantities(connection, ["SKU-1"]) == {"SKU-1": 2}
    finally:
        engine.dispose()


def test_missing_aftersale_table_has_no_returns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'returns.db'}")
    try:
        with engine.connect() as connection:
            assert _aftersale_return_quantities(connection, ["SKU-1"]) == {}
    finally:
        engine.dispose()


def test_style_summary_adds_aftersale_returns_for_each_goods_code():
    summary = _style_summary_item(
        "STYLE-1",
        [
            {"id": 1, "metrics": {"return_qty": 2}},
            {"id": 2, "metrics": {"return_qty": 3}},
        ],
    )

    assert summary["metrics"]["return_qty"] == 5
