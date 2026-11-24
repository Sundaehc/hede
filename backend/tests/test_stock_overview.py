from datetime import date, timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine

from api.routes import stock_overview as routes
from domain.stock_overview import build_overview
from storage.stock_alert_rules import RuleConflict
from storage.stock_alert_tasks import StockAlertTaskRepository, TaskConflict
from storage.stock_overview import StockOverviewPolicyRepository, load_stock_overview
from storage import stock_overview as overview_store

TODAY = date(2026, 11, 20)
BRAND = "cbanner_womens"


def facts(*, regular_7=70, regular_30=300, clearance_30=0, complete=True, stock=(0, 1000), stock_date=TODAY):
    row = {"id": 1, "brand": BRAND, "sku": "SHOE", "year": "2024", "season": "winter", "launch_date": "2024-10-01",
           "supplier": "Maker", "size_group": "G", "sizes": [{"name": "37"}, {"name": "40"}],
           "available_quantity": str(sum(stock)), "stock_by_size": dict(zip(("37", "40"), stock)), "transit_by_size": {},
           "explicit_sizes": ["37", "40"], "size_issues": [], "issues": [], "ambiguous_sales": False, "seen": True,
           "negative_sizes": False, "regular_7": regular_7, "regular_30": regular_30,
           "clearance_7": 0, "clearance_30": clearance_30}
    return {"items": [row], "stock_date": stock_date.isoformat(), "sales_end": (TODAY - timedelta(days=1)).isoformat(),
            "window_complete": {"7": complete, "30": complete}}


def history(recent, *, gross=9300, net=9000, confirmed=False, issues=None):
    return {**recent, "items": [{**recent["items"][0], "listed_days": 770,
                 "gross_sales": str(gross), "net_sales": str(net), "purchase_received_reference": "10000",
                 "sales_issues": issues or [], "inbound_issues": [], "zero_confirmed": confirmed}]}


def policies(**overrides):
    return {("2024", "winter"): {"sale_start": None, "exit_date": TODAY + timedelta(days=30),
            "lead_days": 40, "target_rate": 95, "channel": "outlet", "version": 1, **overrides}}


SUPPLIERS = {"Maker": {"size_ratios": {"G": {"37": 4, "40": 1}}, "lead_days": 15, "cover_days": 14}}


def build(recent, prior=None, rules=None):
    return build_overview(recent, prior or history(recent), {}, SUPPLIERS, rules or {}, TODAY)


def test_exit_uses_target_gap_and_regular_demand_and_protects_core_size():
    recent = facts(stock=(0, 1000), clearance_30=2000)
    result = build(recent, rules=policies())
    rows = result["recommendations"]
    clearance = next(row for row in rows if row["kind"] == "clearance")
    assert clearance["quantity"] == 200
    assert clearance["sizes"] == [{"name": "40", "available": 1000, "quantity": 200}]
    assert {row["kind"] for row in rows} == {"clearance", "review"}
    assert result["inventory"]["total_30"] == 2300
    assert sum(bucket["units"] for bucket in result["inventory"]["buckets"]) == 1000


def test_future_season_does_not_clear_even_inside_exit_lead_time():
    recent = facts(regular_7=0, regular_30=0)
    result = build(recent, rules=policies(sale_start=TODAY + timedelta(days=5), target_rate=100))
    assert not result["recommendations"]
    assert next(bucket for bucket in result["inventory"]["buckets"] if bucket["key"] == "next_season")["units"] == 1000


def test_archive_style_years_share_the_same_exit_rule_and_option():
    recent = facts(regular_7=0, regular_30=0)
    source = recent["items"][0]
    years = ["26年冬季款", "2026冬季款", "2026年", "2026"]
    recent["items"] = [
        {**source, "id": i, "sku": f"SHOE-{i}", "year": year, "season": "冬季"}
        for i, year in enumerate(years, 1)
    ] + [
        {**source, "id": 5, "sku": "SHOE-5", "year": "2026", "season": "0"},
        {**source, "id": 6, "sku": "SHOE-6", "year": "X2026", "season": "冬季"},
    ]
    without_rules = build(recent)
    assert without_rules["scopes"] == [{"year": "2026", "season": "冬季"}]
    rule = next(iter(policies(target_rate=100).values()))
    result = build(recent, rules={("2026", "冬季"): rule})
    cleared = [row for row in result["recommendations"] if row["kind"] == "clearance"]
    assert {row["id"]: row["year"] for row in cleared} == dict(enumerate(years, 1))
    assert all(row["exit_date"] == rule["exit_date"].isoformat() for row in cleared)


def test_clearance_sales_do_not_cause_replenishment_and_missing_sales_is_unknown():
    recent = facts(regular_7=0, regular_30=0, clearance_30=1000)
    assert "replenish" not in {row["kind"] for row in build(recent)["recommendations"]}
    result = build(facts(complete=False), rules=policies(target_rate=100))
    assert {row["kind"] for row in result["recommendations"]} == {"review"}
    assert result["inventory"]["regular_30"] is None
    assert result["inventory"]["coverage_days"] is None


def test_exiting_zero_stock_cannot_create_replenishment_and_missing_size_is_not_zero():
    recent = facts(stock=(0, 0))
    assert {row["kind"] for row in build(recent)["recommendations"]} == {"replenish"}
    assert {row["kind"] for row in build(recent, rules=policies(target_rate=100))["recommendations"]} == {"review"}
    recent["items"][0]["explicit_sizes"] = ["40"]
    assert not build(recent)["recommendations"]


def test_zero_requires_raw_confirmation_and_stale_snapshot_blocks_actions():
    recent = facts(regular_7=0, regular_30=0)
    assert {row["kind"] for row in build(recent, history(recent, net=0, gross=0))["recommendations"]} == {"review"}
    assert {row["kind"] for row in build(recent, history(recent, net=0, gross=0, confirmed=True))["recommendations"]} == {"zero"}
    old = facts(stock_date=TODAY - timedelta(days=1))
    assert {row["kind"] for row in build(old, rules=policies(target_rate=100))["recommendations"]} == {"review"}


def test_workflow_reuses_tasks_history_and_rejects_duplicate_or_opposite_action():
    repo = StockAlertTaskRepository(create_engine("sqlite://"))
    repo.create_tables()
    actor = {"id": 1, "username": "operator"}
    snapshot = {"brand": BRAND, "id": 9, "sku": "SHOE", "quantity": 50}
    def assign(kind):
        return repo.create(kind=kind, assignee=actor, actor=actor, snapshot=snapshot, due_date=TODAY, measures="review")
    item = assign("clearance")
    for kind in ("clearance", "replenish"):
        with pytest.raises(TaskConflict):
            assign(kind)
    active = repo.overview_active(BRAND)
    assert active[(9, "clearance")]["id"] == item["id"]
    assert repo.get(item["id"])["snapshot"]["quantity"] == 50
    repo.save(item["id"], version=1, values={"status": "completed", "result": "done"}, actor=actor)
    first = item["created_at"].date() - timedelta(days=1)
    summary, completed, clearance = repo.overview_week(BRAND, first, first + timedelta(days=6))
    assert (summary["created"], summary["completed"], completed, clearance) == (1, 1, {9}, {9})
    assert assign("replenish")["kind"] == "replenish"


def test_rule_versions_preserve_the_saved_policy():
    repo = StockOverviewPolicyRepository(create_engine("sqlite://"))
    repo.create_tables()
    values = {**policies()[("2024", "winter")], "brand": BRAND, "year": "2024", "season": "winter", "user_id": 1}
    repo.save(**{**values, "version": 0})
    repo.save(**{**values, "target_rate": 80})
    with pytest.raises(RuleConflict):
        repo.save(**values)
    saved = repo.list_rules(BRAND)["2024", "winter"]
    assert (saved["version"], saved["target_rate"]) == (2, 80)


def test_assignment_route_rejects_stale_snapshot_and_revalidates_permissions(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    app.state.repository = type("Catalog", (), {"product_archive_brands": lambda self: [BRAND]})()
    app.state.auth_repository = type("Accounts", (), {"get_user": lambda self, _: {"status": "active", "id": 1, "permissions": ["product.view"]}})()
    candidate = next(row for row in build(facts(), rules=policies())["recommendations"] if row["kind"] == "clearance")
    monkeypatch.setattr(routes, "_overview", lambda *_: ({"recommendations": [candidate]}, {}))
    monkeypatch.setattr(routes, "business_today", lambda: TODAY)

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.current_user = {"id": 1, "permissions": ["product.view", *(["product.manage"] if request.headers.get("test-manager") else [])]}
        return await call_next(request)

    with TestClient(app) as client:
        body = {"brand": BRAND, "product_id": 1, "kind": "clearance", "signature": "0" * 64,
                "assignee_id": 1, "due_date": TODAY.isoformat()}
        url = "/stock-alerts/tasks/from-overview"
        assert client.post(url, json=body).status_code == 403
        assert client.post(url, json=body, headers={"test-manager": "1"}).status_code == 409
        body.update(signature=routes._signature(candidate), due_date=(TODAY + timedelta(days=31)).isoformat())
        assert client.post(url, json=body, headers={"test-manager": "1"}).status_code == 400


def test_batch_assigns_by_kind_and_keeps_successes_when_other_rows_fail(monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.pool import StaticPool

    app = FastAPI()
    app.include_router(routes.router)
    app.state.repository = SimpleNamespace(product_archive_brands=lambda: [BRAND])
    app.state.auth_repository = SimpleNamespace(get_user=lambda user_id: {
        "status": "active", "id": user_id, "username": "operator", "permissions": ["product.view"]})
    repo = app.state.stock_alert_tasks = StockAlertTaskRepository(create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}))
    repo.create_tables()
    actor = {"id": 1, "username": "manager"}
    repo.create(snapshot={"brand": BRAND, "id": 4, "sku": "SHOE-4"}, kind="clearance",
        assignee=actor, due_date=TODAY, measures="", actor=actor)
    repo.create(snapshot={"brand": BRAND, "id": 6, "sku": "SHOE-6"}, kind="slow",
        assignee=actor, due_date=TODAY, measures="", actor=actor)
    due = (TODAY + timedelta(days=3)).isoformat()
    selections = [(1, "slow"), (1, "clearance"), (2, "zero"), (3, "clearance"), (4, "replenish"), (6, "slow"), (7, "zero")]
    rows = [{"brand": BRAND, "id": number, "sku": f"SHOE-{number}", "kind": kind,
             "due_date": TODAY.isoformat() if number == 3 else due, "quantity": 10}
            for number, kind in selections if number != 7]
    signed = {(row["id"], row["kind"]): routes._signature(row) for row in rows}
    items = [{"product_id": number, "kind": kind,
              "signature": signed[(number, kind)] if number not in (2, 7) else "0" * 64}
             for number, kind in selections]
    calls = []
    monkeypatch.setattr(routes, "_overview", lambda *_: (calls.append(1) or {"recommendations": rows}, {}))
    monkeypatch.setattr(routes, "business_today", lambda: TODAY)
    monkeypatch.setattr("api.routes.stock_alert_tasks.write_operation_log", lambda *_, **__: None)

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.current_user = {**actor, "permissions": ["product.view", *(
            ["product.manage"] if request.headers.get("test-manager") else [])]}
        return await call_next(request)

    url = "/stock-alerts/tasks/batch-from-overview"
    body = {"brand": BRAND, "assignee_id": 8, "due_date": due, "measures": " review ", "items": items}
    headers = {"test-manager": "1"}
    with TestClient(app) as client:
        assert client.post(url, json=body).status_code == 403
        assert client.post(url, json={**body, "items": [items[0], items[0]]}, headers=headers).status_code == 400
        result = client.post(url, json=body, headers=headers)
        assert result.status_code == 200
        payload = result.json()
        assert payload["total"] == 7
        assert payload["succeeded"] == ["1/slow", "1/clearance"]
        failures = {row["id"]: row["reason"] for row in payload["failed"]}
        assert set(failures) == {"2/zero", "3/clearance", "4/replenish", "6/slow", "7/zero"}
        assert failures["2/zero"] == failures["7/zero"] and "重新勾选" in failures["2/zero"]
        assert "最晚处理日" in failures["3/clearance"]
        assert "相反" in failures["4/replenish"]
        assert "已有未完成" in failures["6/slow"]
        assert len(calls) == 1
    active = repo.overview_active(BRAND)
    assert set(active) == {(1, "slow"), (1, "clearance"), (4, "clearance"), (6, "slow")}
    for key in ((1, "slow"), (1, "clearance")):
        task = repo.get(active[key]["id"])
        assert task["assignee_id"] == 8 and task["measures"] == "review"
        assert routes._signature(task["snapshot"]) == signed[key]
        assert repo.events(task["id"])["items"][0]["action"] == "created"


def test_overview_cache_reuses_recommendations_but_reads_new_rules(monkeypatch):
    class Repository:
        engine = object()

    recent = facts()
    calls = []
    monkeypatch.setattr(overview_store, "_overview_facts", lambda *args: (calls.append(args) or recent, history(recent)))
    repository = Repository()
    rule_values = {}

    def read_rules():
        return {}, SUPPLIERS, dict(rule_values)

    original, _ = load_stock_overview(repository, BRAND, TODAY, refresh=False, read_rules=read_rules)
    again, _ = load_stock_overview(repository, BRAND, TODAY, refresh=False, read_rules=read_rules)
    assert again == original and len(calls) == 1
    assert any(row["kind"] == "replenish" for row in original["recommendations"])
    rule_values.update(policies())
    edited, _ = load_stock_overview(repository, BRAND, TODAY, refresh=False, read_rules=read_rules)
    assert len(calls) == 1
    assert any(row["kind"] == "clearance" for row in edited["recommendations"])
    load_stock_overview(repository, BRAND, TODAY + timedelta(days=1), refresh=False, read_rules=read_rules)
    assert len(calls) == 2


def test_overview_pages_keep_priority_when_crossing_live_task_and_review_groups(monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace

    from domain.sources import IMAGE_BRAND_KEYS

    kinds = ["clearance"] * 20 + ["zero"] * 12 + ["review"] * 6
    rows = [{"id": i, "sku": f"item{i}", "kind": kind, "reason": "reason"}
            for i, kind in enumerate(kinds)]
    active = {(i, kinds[i]): {"id": i + 100} for i in (1, 3, 25)}
    active[(2, "replenish")] = {"id": 102}
    lookups = []

    def image_paths(brand, ids):
        lookups.append((brand, ids))
        return {0: "/photos/stock/photo #1.jpg"} if 0 in ids else {}

    state = SimpleNamespace(
        stock_alert_tasks=SimpleNamespace(overview_active=lambda _: active),
        repository=SimpleNamespace(product_image_paths_by_id=image_paths),
        settings=SimpleNamespace(image_roots={IMAGE_BRAND_KEYS[BRAND]: Path("/photos/stock")}),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    payload = {"recommendations": rows, "inventory": {}}
    monkeypatch.setattr(routes, "_actor", lambda _: None)
    monkeypatch.setattr(routes, "_validate_brand", lambda *_: None)
    monkeypatch.setattr(routes, "_overview", lambda *_: (payload, {}))
    first = json.loads(routes.stock_overview(request, BRAND, "all", "", 1).body)
    second = json.loads(routes.stock_overview(request, BRAND, "all", "", 2).body)
    assert first["total"] == second["total"] == len(rows)
    assert first["assignable"] == 28 and first["in_progress"] == 4
    assert [row["id"] for row in first["items"] + second["items"]] == sorted(
        range(len(rows)), key=lambda i: 2 if kinds[i] == "review" else int(i in {1, 2, 3, 25}))
    assert lookups == [(BRAND, {row["id"] for row in page["items"]}) for page in (first, second)]
    assert first["items"][0]["image_url"] == f"/images/serve/{BRAND}/photo%20%231.jpg"
    assert first["items"][1]["image_url"] is None
    assert "image_url" not in rows[0]  # Presentation fields must not mutate cached calculations.
    assert next(row for row in second["items"] if row["id"] == 2)["task"] == {"id": 102}
