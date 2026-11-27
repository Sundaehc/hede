from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from openpyxl import Workbook
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, select

from domain.sources import SheetSpec, WorkbookSpec
from scripts import refresh_product_size_fields as refresh
from scripts import sync_products_and_copywriting_daily as workflow
from transform.rows import CBANNER_WOMENS_STYLE_FIELD_LABELS


def test_shared_archive_refresh_updates_only_matching_active_products(tmp_path, monkeypatch):
    brand = "cbanner_womens"
    spec = WorkbookSpec(brand, "womens", brand, (SheetSpec("千百度"),))
    monkeypatch.setattr(refresh, "WORKBOOK_SPECS", (spec,))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "千百度"
    sheet.append(["货号", "原始货号", "跟高", "后跟高", "跟底款式", "鞋帮", "品名"])
    sheet.append(["A", "ORIGINAL-A", 4.5, "中跟", "粗跟", 6, "共享品名"])
    sheet.append(["B1", "SHARED", 2])
    sheet.append(["B2", "SHARED", 5])
    workbook.save(tmp_path / "womens.xlsx")
    sources, _ = refresh.load_source_size_records(
        settings=SimpleNamespace(excel_root=tmp_path), include_womens_style=True,
    )
    fields = refresh.FIELD_LABELS.keys() | CBANNER_WOMENS_STYLE_FIELD_LABELS.keys()
    table = Table(
        "products", MetaData(), Column("id", Integer, primary_key=True),
        *(Column(name, String) for name in ("sku", "original_sku", "product_name", *sorted(fields))),
        Column("deleted_at", DateTime), Column("updated_at", DateTime),
    )
    monkeypatch.setitem(refresh.PRODUCT_TABLES, brand, table)
    with create_engine("sqlite://").begin() as connection:
        connection.connection.driver_connection.create_function("date_trunc", 2, lambda _, value: value)
        table.create(connection)
        connection.execute(table.insert(), [
            {"id": 1, "sku": "WEB-A", "original_sku": "ORIGINAL-A", "heel_height": "2", "upper_height": "低帮", "product_name": "网页品名"},
            {"id": 2, "sku": "WEB-B", "original_sku": "SHARED", "heel_height": "1", "upper_height": None, "product_name": None},
            {"id": 3, "sku": "B2", "original_sku": "SHARED", "heel_height": "1", "upper_height": None, "product_name": None},
        ])
        connection.execute(table.insert().values(id=4, sku="A", heel_height="1", deleted_at=date(2026, 11, 25)))
        stats = refresh._update_archive_fields(connection, [brand], sources, False, True)[brand]
        rows = connection.execute(select(table).order_by(table.c.id)).mappings().all()
        assert stats.updated_rows == 2
        assert [row["heel_height"] for row in rows] == ["4.5", "1", "5", "1"]
        assert rows[0]["rear_heel_height"] == "中跟"
        assert rows[0]["sole_style"] == "粗跟"
        assert rows[0]["upper_height"] == "低帮"
        assert rows[0]["product_name"] == "网页品名"
        assert refresh._update_archive_fields(connection, [brand], sources, False, True)[brand].updated_rows == 0


def test_daily_workflow_retries_shared_archive_then_runs_other_steps(monkeypatch):
    business_date = date(2026, 11, 25)
    successes = set()
    statuses = Mock(
        is_success=Mock(side_effect=lambda name, _: name in successes),
        mark_finished=Mock(side_effect=lambda name, _, status, **kwargs: successes.add(name) if status == "success" else None),
    )
    settings = Mock()
    refresh_fields = Mock(side_effect=[OSError("share unavailable"), ({}, {})])
    images = Mock(side_effect=lambda *_: successes.add(workflow.IMAGE_TASK_NAME) or 0)
    generation = Mock(return_value={})
    tags = Mock(return_value={"products": 0, "tag_definitions": 0})
    quality = Mock(side_effect=lambda *_: successes.add(workflow.QUALITY_TASK_NAME) or 0)
    monkeypatch.setattr(workflow, "business_today", lambda: business_date)
    monkeypatch.setattr(workflow, "check_quality_reports", quality)
    monkeypatch.setattr(workflow, "refresh_product_size_fields", refresh_fields)
    monkeypatch.setattr(workflow, "run_import", images)
    monkeypatch.setattr(workflow, "run_daily_generation", generation)
    monkeypatch.setattr(workflow, "run_daily_tag_sync", tags)

    assert workflow.run_workflow(settings, statuses, business_date) == 1
    images.assert_not_called()
    quality.assert_not_called()
    assert workflow.run_workflow(settings, statuses, business_date) == 0
    assert workflow.ARCHIVE_FIELDS_TASK_NAME in successes
    assert workflow.run_workflow(settings, statuses, business_date) == 0
    assert refresh_fields.call_count == 2
    refresh_fields.assert_called_with(dry_run=False, settings=settings, include_womens_style=True)
    images.assert_called_once()
    generation.assert_called_once()
    tags.assert_called_once()
    quality.assert_called_once_with(settings, statuses, business_date)


def test_failed_quality_audit_retries_without_repeating_product_maintenance(monkeypatch):
    business_date = date(2026, 11, 27)
    successes = {workflow.ARCHIVE_FIELDS_TASK_NAME, workflow.IMAGE_TASK_NAME}
    statuses = Mock(
        is_success=Mock(side_effect=lambda name, _: name in successes),
        mark_finished=Mock(side_effect=lambda name, _, status, **kwargs: successes.add(name) if status == "success" else successes.discard(name)),
    )
    settings = Mock()
    generation = Mock(return_value={})
    tags = Mock(return_value={"products": 0, "tag_definitions": 0})
    quality = Mock(side_effect=[1, 0])
    monkeypatch.setattr(workflow, "business_today", lambda: business_date)
    monkeypatch.setattr(workflow, "run_daily_generation", generation)
    monkeypatch.setattr(workflow, "run_daily_tag_sync", tags)
    monkeypatch.setattr(workflow, "check_quality_reports", quality)

    assert workflow.run_workflow(settings, statuses, business_date) == 1
    assert workflow.TASK_NAME not in successes
    statuses.mark_finished.assert_called_with(workflow.TASK_NAME, business_date, status="failed", message=(
        "商品档案、图片、提示词及标签已完成，质检报告巡检未成功，等待下次计划重试"
    ))
    assert workflow.run_workflow(settings, statuses, business_date) == 0
    generation.assert_called_once()
    tags.assert_called_once()
    assert quality.call_count == 2


def test_existing_same_day_workflow_success_runs_only_new_quality_step(monkeypatch):
    business_date = date(2026, 11, 27)
    statuses = Mock(is_success=Mock(side_effect=lambda task, _: task == workflow.TASK_NAME))
    settings = Mock()
    quality = Mock(return_value=0)
    monkeypatch.setattr(workflow, "business_today", lambda: business_date)
    monkeypatch.setattr(workflow, "check_quality_reports", quality)

    assert workflow.run_workflow(settings, statuses, business_date) == 0
    quality.assert_called_once_with(settings, statuses, business_date)
    assert {call.args[0] for call in statuses.is_success.call_args_list} == {workflow.TASK_NAME, workflow.QUALITY_TASK_NAME}
