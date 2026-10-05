import asyncio
import io
from types import SimpleNamespace

from openpyxl import load_workbook

from api.routes.suppliers import export_suppliers


class _SupplierRepository:
    def get_supplier_brand_by_code(self, code):
        return {"name": code}

    def list_suppliers_page(self, **kwargs):
        assert kwargs["include_balances"] is True
        assert kwargs["date_start"] == "2026-10-01"
        assert kwargs["date_end"] == "2026-10-05"
        return {"items": [{
            "name": "测试供应商", "factory_code": "A01",
            "beginning_balance": "100", "period_amount": "-25", "ending_balance": "75",
            "contact": "不应导出", "notes": "不应导出",
        }], "total": 1}


def test_supplier_export_contains_balances_without_hidden_fields():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        inventory_repository=_SupplierRepository(), operation_log_repository=None,
    )))
    response = export_suppliers(request, date_start="2026-10-01", date_end="2026-10-05")

    async def read_content():
        return b"".join([chunk async for chunk in response.body_iterator])

    workbook = load_workbook(io.BytesIO(asyncio.run(read_content())), data_only=True)
    worksheet = workbook.active
    assert [cell.value for cell in worksheet[1]] == [
        "供应商名称", "工厂代码", "期初余额", "本期发生额", "期末余额",
    ]
    assert [cell.value for cell in worksheet[2]] == ["测试供应商", "A01", 100, -25, 75]
