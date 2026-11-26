"""Generate and assign stock candidates after source refreshes."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import logging

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect

from api.routes.auth import user_has_permission
from storage.auth_repository import AuthRepository
from storage.product_repository import ProductRepository
from storage.stock_alert_rules import StockAlertRuleRepository
from storage.stock_alert_tasks import StockAlertTaskRepository, business_today
from storage.stock_operating_rules import ASSIGNMENT, StockOperatingRepository
from storage.stock_overview import StockOverviewPolicyRepository, load_stock_overview
from storage.stock_replenishment_rules import StockReplenishmentRuleRepository

logger = logging.getLogger(__name__)


def collect_candidates(data, rules, today):
    selected = {}
    enabled = {rule["kind"]: rule for rule in rules if rule["enabled"]}
    for row in data["recommendations"]:
        kind = row["kind"]
        if kind not in enabled:
            continue
        rule = enabled[kind]
        due = today + timedelta(days=rule["due_days"])
        if row["due_date"] and kind == "clearance":
            due = min(due, date.fromisoformat(row["due_date"]))
        selected[kind, row["id"]] = (jsonable_encoder(row), due)
    return selected


def run_stock_auto_assignment(database_url, today=None):
    today = today or business_today()
    repository = ProductRepository(database_url)
    engine = repository.engine
    auth = None
    try:
        if not inspect(engine).has_table(ASSIGNMENT.name):
            # Automatic assignment is enabled only after the feature has loaded.
            return {}
        operating = StockOperatingRepository(engine)
        configured = defaultdict(list)
        for rule in operating.assignments():
            if rule["enabled"]:
                configured[rule["brand"]].append(rule)
        if not configured:
            return {}
        tasks = StockAlertTaskRepository(engine)
        alert = StockAlertRuleRepository(engine)
        supplier = StockReplenishmentRuleRepository(engine)
        policy = StockOverviewPolicyRepository(engine)
        auth = AuthRepository(database_url)
        available_brands = set(repository.product_archive_brands())
        users = {}
        counts = Counter()
        for brand, rules in configured.items():
            if brand not in available_brands:
                continue
            data, _ = load_stock_overview(repository, brand, today, refresh=True,
                read_rules=lambda: (alert.list_rules(brand), supplier.list_rules(brand), policy.list_rules(brand)),
                read_decisions=lambda: operating.decisions(brand))
            sources = data["sources"]
            if not sources["aligned"] or not sources["history_aligned"] or data["inventory"]["total_30"] is None:
                continue
            people = {}
            for rule in rules:
                user_id = rule["assignee_id"]
                if user_id not in users:
                    users[user_id] = auth.get_user(user_id)
                assignee = users[user_id]
                if assignee and assignee.get("status") == "active" and user_has_permission(assignee, "product.view"):
                    people[rule["kind"]] = (assignee, {"id": rule["updated_by"], "display_name": "库存自动派办"})
            candidates = collect_candidates(data, rules, today)
            # A data-quality problem is not evidence that an existing issue disappeared.
            for row in data["recommendations"]:
                if row["kind"] == "review":
                    for kind in people:
                        candidates.setdefault((kind, row["id"]), None)
            for product_id, kinds in data["unobservable"].items():
                for kind in kinds:
                    candidates.setdefault((kind, int(product_id)), None)
            observable = set(people)
            versions = {rule["kind"]: rule["version"] for rule in rules}
            for task in operating.reconcile(brand, candidates, observable_kinds=observable, tasks=tasks,
                                            people=people, rule_versions=versions):
                counts[task["assignee_id"]] += 1
        return dict(counts)
    finally:
        engine.dispose()
        if auth is not None:
            auth.engine.dispose()


def after_stock_source_refresh(database_url):
    try:
        print(f"[OK] stock auto-assignment new tasks by assignee: {run_stock_auto_assignment(database_url)}")
    except Exception:
        logger.exception("Stock source imported, but stock auto-assignment did not complete")


if __name__ == "__main__":
    from config import load_settings

    print(run_stock_auto_assignment(load_settings(require_database=True).database_url))

