from sqlalchemy import create_engine, text

from storage.inventory_repository import InventoryRepository


def test_supplier_balance_summaries_follow_ledger_signs_and_date_boundaries():
    engine = create_engine("sqlite:///:memory:")
    repository = InventoryRepository.__new__(InventoryRepository)
    repository.engine = engine
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE inventory_records (
                id INTEGER PRIMARY KEY, supplier TEXT, date_value DATE,
                date TEXT, document_number TEXT, document_type TEXT,
                summary TEXT, handler TEXT, warehouse TEXT,
                amount NUMERIC, deleted_at TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE inventory_details (
                id INTEGER PRIMARY KEY, document_id INTEGER, amount NUMERIC
            )
        """))
        connection.execute(text("""
            INSERT INTO inventory_records (id, supplier, date_value, document_type, amount, deleted_at)
            VALUES
                (1, '甲', '2026-09-30', '进货单', 100, NULL),
                (2, '甲', '2026-10-01', '进货单', 999, NULL),
                (3, '甲', '2026-10-02', '进货退货单', -20, NULL),
                (4, '甲', '2026-10-03', '应付款减少', 10, NULL),
                (5, '甲', '2026-10-04', '应付款增加', 5, NULL),
                (6, '甲', '2026-10-04', '同价调拨单', 1000, NULL),
                (7, '甲', '2026-10-04', '进货单', 40, '2026-10-05'),
                (8, '甲', '2026-10-06', '进货单', 30, NULL),
                (9, '乙', '2026-10-01', '进货单', 7, NULL)
        """))
        connection.execute(text("INSERT INTO inventory_details (id, document_id, amount) VALUES (1, 2, 50)"))

        dated = repository._supplier_balance_summaries(
            connection, ["甲", "乙", "丙"], date_start="2026-10-01", date_end="2026-10-05",
        )
        current = repository._supplier_balance_summaries(
            connection, ["甲", "乙"], date_start=None, date_end=None,
        )
        before_end = repository._supplier_balance_summaries(
            connection, ["甲"], date_start=None, date_end="2026-10-03",
        )
        from_start = repository._supplier_balance_summaries(
            connection, ["甲"], date_start="2026-10-01", date_end=None,
        )

    assert dated["甲"] == {
        "beginning_balance": "100", "period_amount": "25", "ending_balance": "125",
    }
    assert dated["乙"] == {
        "beginning_balance": "0", "period_amount": "7", "ending_balance": "7",
    }
    assert "丙" not in dated
    assert current["甲"] == {
        "beginning_balance": "0", "period_amount": "155", "ending_balance": "155",
    }
    assert before_end["甲"] == {
        "beginning_balance": "0", "period_amount": "120", "ending_balance": "120",
    }
    assert from_start["甲"] == {
        "beginning_balance": "100", "period_amount": "55", "ending_balance": "155",
    }
    ledger = repository.get_counterparty_ledger(
        counterparty_type="supplier", name="甲", date_start="2026-10-01", date_end="2026-10-05",
    )
    assert dated["甲"]["beginning_balance"] == ledger["beginning_balance"]
    assert dated["甲"]["ending_balance"] == ledger["ending_balance"]
    assert dated["甲"]["period_amount"] == "25"
    engine.dispose()
