from datetime import datetime, timezone
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from api.routes.products import router
from storage.stock_quality_reports import StockQualityReports


PASS = "合格_A RH661673D52 BRH661673D28_3026052326"
FAIL = "甲醛和短链氯化石蜡不合格_A RH661673D52 BRH661673D28_3026055775"


def _workbook(path: Path, rows, result_header="检查结果"):
    workbook = Workbook()
    workbook.active.append(["货号", "原始货号", result_header])
    for row in rows:
        workbook.active.append(row)
    workbook.save(path)
    workbook.close()


def test_reports_link_by_archive_original_and_split_multi_report_cells(tmp_path):
    summaries = tmp_path / "质检报告汇总"
    summaries.mkdir()
    source = summaries / "千百度质检表格汇总.xlsx"
    _workbook(source, [
        ("CHILD", "RH661673D52", f"{PASS}\r\n{FAIL}"),
        ("ANOTHER", "RH661673D52、RH661673D28", f"{PASS}.pdf"),
        ("UNRELATED", "OTHER", "不同货号.pdf"),
    ])
    directory = summaries / "千百度的质检报告"
    directory.mkdir()
    pass_file = directory / f"{PASS}.pdf"
    pass_file.write_bytes(b"%PDF-original")
    modified_at = datetime(2026, 11, 25, 2, 45, 43, tzinfo=timezone.utc)
    os.utime(pass_file, (modified_at.timestamp(), modified_at.timestamp()))
    (directory / f"{PASS}(2).pdf").write_bytes(b"%PDF-copy")
    (directory / f"{FAIL}.pdf").write_bytes(b"%PDF-fail")
    (directory / "不同货号.pdf").write_bytes(b"%PDF-unrelated")
    service = StockQualityReports(tmp_path)

    app = FastAPI()
    app.include_router(router)
    app.state.stock_quality_reports = service
    app.state.repository = SimpleNamespace(
        is_product_archive_brand=lambda brand: brand in {"cbanner_womens", "eblan"},
        get_product=lambda brand, product_id: {
            12: {"sku": "CHILD", "original_sku": "rh661673d52"},
            13: {"sku": "RH661673D52", "original_sku": None},
            14: {"sku": "UNRELATED", "original_sku": "OTHER"},
        }.get(product_id),
    )

    @app.middleware("http")
    async def actor(request, call_next):
        permission = request.headers.get("X-Test-User")
        request.state.current_user = {"id": 1, "permissions": [permission]} if permission else None
        return await call_next(request)

    with TestClient(app, headers={"X-Test-User": "product.view"}) as client:
        base = "/products/cbanner_womens"
        listing = client.get(f"{base}/12/quality-reports").json()["items"]
        assert [(item["name"], item["status"]) for item in listing] == [(PASS, "matched"), (FAIL, "matched")]
        assert [ref["row"] for ref in listing[0]["sources"]] == [2, 3]
        assert listing[0]["modified_at"] == modified_at.isoformat()
        for item, expected in zip(listing, (b"%PDF-original", b"%PDF-fail"), strict=True):
            assert item["file_name"].endswith(".pdf") and "path" not in item
            url = f"{base}/12/quality-reports/{item['id']}"
            response = client.get(url)
            assert response.status_code == 200 and response.content == expected
            assert response.headers["content-disposition"].startswith("inline")
            download = client.get(url, params={"download": "true"})
            assert download.status_code == 200 and download.content == expected
            assert download.headers["content-disposition"].startswith("attachment")
            assert client.get(url.replace("cbanner_womens", "eblan")).status_code == 404
            assert client.get(url.replace("/12/", "/14/")).status_code == 404
            assert client.get(url, headers={"X-Test-User": ""}).status_code == 401
            assert client.get(url, headers={"X-Test-User": "inventory.view"}).status_code == 403
        assert client.get("/stock-alerts/overview/items/12/quality-reports?brand=cbanner_womens").status_code == 404
        assert client.get(f"{base}/13/quality-reports").json() == {"original_sku": "", "items": []}


def test_number_fallback_keeps_missing_and_ambiguous_results_visible(tmp_path):
    summaries = tmp_path / "质检报告汇总"
    summaries.mkdir()
    _workbook(summaries / "烟斗质检货号汇总.xlsx", [("CHILD", "001234", "\n".join([
        "原表_3026059999", "缺文件_3026058888", "同名.pdf", "编号冲突_3026057777",
        "同内容.pdf",
    ]))], result_header="检测结果")
    (tmp_path / "新名称_3026059999.docx").write_bytes(b"new name")
    src = tmp_path / "历史"
    src.mkdir()
    for path, data in [(tmp_path, b"first"), (src, b"other")]:
        (path / "同名.pdf").write_bytes(data)
        (path / "同内容.pdf").write_bytes(b"identical")
        (path / f"{data.decode()}_3026057777.pdf").write_bytes(data)
    reports = StockQualityReports(tmp_path).for_product("001234", "yandou")

    assert [report.status for report in reports] == ["number_match", "missing", "ambiguous", "ambiguous", "matched"]
    assert reports[0].path.name == "新名称_3026059999.docx"
    assert reports[-1].path.name == "同内容.pdf"

