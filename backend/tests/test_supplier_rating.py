from __future__ import annotations

from storage.inventory_repository import InventoryRepository


def supplier_grade(metrics: dict[str, object], status: str = "") -> str:
    grade, _suggestion = InventoryRepository._supplier_grade_and_suggestion(
        {"cooperation_status": status},
        metrics,
    )
    return grade


def test_supplier_rating_keeps_stopped_suppliers_as_d() -> None:
    assert supplier_grade(
        {
            "style_count": 30,
            "sales_30d": 800,
            "stock_qty": 100,
            "reject_rate": 0.01,
        },
        status="暂停",
    ) == "D"


def test_supplier_rating_score_thresholds() -> None:
    assert supplier_grade({
        "style_count": 30,
        "sales_30d": 600,
        "stock_qty": 500,
        "reject_rate": 0.05,
    }) == "A"

    assert supplier_grade({
        "style_count": 10,
        "sales_30d": 200,
        "stock_qty": 300,
        "reject_rate": 0.1,
    }) == "B"

    assert supplier_grade({
        "style_count": 3,
        "sales_30d": 60,
        "stock_qty": 500,
        "reject_rate": 0.16,
    }) == "C"

    assert supplier_grade({
        "style_count": 25,
        "sales_30d": 0,
        "stock_qty": 1200,
        "reject_rate": None,
    }) == "D"
