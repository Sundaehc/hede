from datetime import date

import pytest
from sqlalchemy import create_engine

from domain.stock_alerts import ArchiveMatcher
from domain.stock_portfolio import UNKNOWN, portfolio_page, replenishment_block
from domain.stock_replenishment import select_replenishment
from storage.stock_alert_rules import RuleConflict
from storage.stock_alert_tasks import StockAlertTaskRepository, TaskConflict
from storage.stock_operating_rules import StockOperatingRepository

TODAY = date(2026, 11, 25)
ACTOR = {"id": 1, "username": "manager"}
OWNER = {"id": 2, "username": "owner"}
SNAPSHOT = {"id": 16, "brand": "cbanner_womens", "sku": "NEW", "original_sku": "OLD"}


def test_portfolio_groups_original_codes_without_counting_multi_season_twice():
    base = {"year": "26年春季款", "season": "春秋", "category": "单鞋", "color": "", "product_name": "测试款",
            "status": "selling", "available_quantity": 12, "historic_received": 20, "historic_net": 5}
    rows = [base | {"id": 1, "sku": "OLD", "original_sku": "old"},
            base | {"id": 2, "sku": "NEW", "original_sku": "OLD", "status": "confirmed", "available_quantity": 3},
            base | {"id": 3, "sku": "OLD", "original_sku": None, "year": None, "product_name": "", "available_quantity": 99}]
    autumn = portfolio_page(rows, year="2026", season="秋", category="测试款", query="NEW")
    assert autumn["total"] == 1
    assert autumn["items"][0] == {"product_id": 1, "sku": "old", "product_name": "测试款", "available_quantity": 15,
                                  "children": 2, "confirmed_clearance_quantity": 3, "statuses": ["confirmed", "selling"]}
    assert autumn["totals"] == {"selling": 12, "confirmed": 3}
    assert set(autumn["categories"]) == {"测试款", UNKNOWN}
    assert portfolio_page(rows, category="单鞋")["total"] == 0
    assert portfolio_page(rows, category=UNKNOWN)["items"][0]["product_id"] == 3
    assert autumn["sell_through"] == 25
    assert sum(portfolio_page(rows)["totals"].values()) == 114
    assert portfolio_page(rows, year=UNKNOWN)["items"][0]["product_id"] == 3


def test_matching_keeps_exact_old_code_inside_one_family_but_blocks_cross_brand():
    parent = {"brand": "cbanner_womens", "id": 1, "sku": "OLD", "original_sku": "OLD"}
    child = parent | {"id": 2, "sku": "NEW"}
    assert ArchiveMatcher([parent, child], {}).resolve("OLD") == ("cbanner_womens", 1)
    assert ArchiveMatcher([parent, child | {"brand": "eblan"}], {}).resolve("OLD") is None
    assert ArchiveMatcher([child, child | {"id": 3, "sku": "NEWER"}], {}).resolve("OLD") is None


def test_confirmed_clearance_blocks_replenishment_and_does_not_add_to_moq():
    item = SNAPSHOT | {"supplier": "supplier", "year": "2026", "season": "冬"}
    decisions = {16: {"confirmed": True}}
    reason = replenishment_block(item, {}, decisions, TODAY)
    rules = {"supplier": {"min_order_qty": 30}}
    result = select_replenishment({"items": [item]}, rules, status="all", blocked={16: reason})
    assert result["items"][0]["suggested_quantity"] is None
    assert result["items"][0]["blocked_reason"] == reason
    assert result["supplier_summaries"][0]["moq_gap"] == 30
    assert replenishment_block(item, {("2026", "冬"): {
        "exit_date": "2026-12-01", "sale_start": None, "lead_days": 8}}, {}, TODAY) == "已进入库存退出期"


def test_auto_assignment_reuses_active_and_completed_while_issue_persists():
    engine = create_engine("sqlite://")
    tasks = StockAlertTaskRepository(engine)
    tasks.create_tables()
    operating = StockOperatingRepository(engine)
    key = ("zero", 16)
    selected = {key: (SNAPSHOT, TODAY)}
    kwargs = {"observable_kinds": {"zero"}, "tasks": tasks, "people": {"zero": (OWNER, ACTOR)}}
    existing = tasks.create(snapshot=SNAPSHOT, kind="zero", assignee=OWNER, due_date=TODAY, measures="", actor=ACTOR)
    assert operating.reconcile(SNAPSHOT["brand"], selected, **kwargs) == []
    assert tasks.reminders(OWNER["id"])["open"] == 1
    tasks.save(existing["id"], version=1, values={"status": "completed", "measures": "检查", "result": "已处理"}, actor=ACTOR)
    assert operating.reconcile(SNAPSHOT["brand"], selected, **kwargs) == []
    assert operating.reconcile(SNAPSHOT["brand"], {key: None}, **kwargs) == []
    assert operating.reconcile(SNAPSHOT["brand"], selected, **kwargs) == []
    assert operating.reconcile(SNAPSHOT["brand"], {}, **kwargs) == []
    assert len(operating.reconcile(SNAPSHOT["brand"], selected, **kwargs)) == 1
    engine.dispose()


def test_clearance_is_versioned_and_blocks_a_stale_assignment():
    engine = create_engine("sqlite://")
    tasks = StockAlertTaskRepository(engine)
    tasks.create_tables()
    operating = StockOperatingRepository(engine)
    operating.save_clearance(SNAPSHOT["brand"], 16, 0, 1, confirmed=True, reason="退场")
    with pytest.raises(RuleConflict):
        operating.save_clearance(SNAPSHOT["brand"], 16, 0, 1, confirmed=False, reason="变更")
    with pytest.raises(TaskConflict, match="清仓"):
        tasks.create(snapshot=SNAPSHOT, kind="replenish", assignee=OWNER, due_date=TODAY, measures="", actor=ACTOR)
    operating.save_clearance(SNAPSHOT["brand"], 16, 1, 1, confirmed=False, reason="复核继续销售")
    assert tasks.create(snapshot=SNAPSHOT, kind="replenish", assignee=OWNER, due_date=TODAY, measures="", actor=ACTOR)
    engine.dispose()


def test_auto_assignment_does_not_use_a_rule_disabled_during_calculation():
    engine = create_engine("sqlite://")
    tasks = StockAlertTaskRepository(engine)
    tasks.create_tables()
    operating = StockOperatingRepository(engine)
    brand = SNAPSHOT["brand"]
    operating.save_assignment(brand, "zero", 0, ACTOR["id"], enabled=True, assignee_id=OWNER["id"], due_days=2)
    operating.save_assignment(brand, "zero", 1, ACTOR["id"], enabled=False, assignee_id=OWNER["id"], due_days=2)
    assert operating.reconcile(brand, {("zero", 16): (SNAPSHOT, TODAY)}, observable_kinds={"zero"},
                               tasks=tasks, people={"zero": (OWNER, ACTOR)}, rule_versions={"zero": 1}) == []
    assert tasks.reminders(OWNER["id"])["open"] == 0
    engine.dispose()

