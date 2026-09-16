from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from api.routes.inventory import export_general_customer_ledger


class _LedgerRepository:
    def get_counterparty_ledger(self, **kwargs):
        assert kwargs == {
            "counterparty_type": "customer",
            "name": "杭州一店",
            "date_start": "2026-09-01",
            "date_end": "2026-09-16",
        }
        return {
            "items": [{
                "id": 18,
                "row_number": 1,
                "date": "2026-09-08",
                "document_number": "PFXSD-2026-09-08-0001",
                "document_type": "批发销售单",
                "summary": "秋季补货",
                "handler": "财务甲",
                "warehouse": "千百度公司仓库",
                "increase_amount": "1200.50",
                "decrease_amount": "",
                "balance": "1500.50",
            }],
            "beginning_balance": "300",
            "increase_total": "1200.50",
            "decrease_total": "0",
            "ending_balance": "1500.50",
        }


def _request(*, department_code: str, role_code: str = "member"):
    return SimpleNamespace(
        state=SimpleNamespace(current_user={
            "department_code": department_code,
            "role_code": role_code,
        }),
        app=SimpleNamespace(state=SimpleNamespace(
            inventory_repository=_LedgerRepository(),
            operation_log_repository=None,
        )),
    )


async def _response_bytes(response) -> bytes:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.encode() if isinstance(chunk, str) else chunk)
    return b"".join(chunks)


def test_general_customer_ledger_export_rejects_non_finance_department() -> None:
    with pytest.raises(HTTPException) as exc_info:
        export_general_customer_ledger(
            _request(department_code="商品部"),
            name="杭州一店",
            date_start="2026-09-01",
            date_end="2026-09-16",
        )

    assert exc_info.value.status_code == 403


def test_finance_department_can_export_general_customer_ledger() -> None:
    response = export_general_customer_ledger(
        _request(department_code="财务部"),
        name="杭州一店",
        date_start="2026-09-01",
        date_end="2026-09-16",
    )
    content = asyncio.run(_response_bytes(response))
    workbook = load_workbook(io.BytesIO(content), data_only=True)
    worksheet = workbook["应收款明细账本"]

    assert [cell.value for cell in worksheet[1]] == [
        "行号", "日期", "单据编号", "单据类型", "单据摘要",
        "经手人", "仓库", "增加金额", "减少金额", "余额",
    ]
    assert worksheet["C2"].value == "PFXSD-2026-09-08-0001"
    assert worksheet["H2"].value == 1200.5
    assert worksheet["I2"].value is None
    assert worksheet["A3"].value == "合计"
    assert worksheet["J3"].value == 1500.5
    assert "杭州一店" in response.headers["content-disposition"] or "%E6%9D%AD%E5%B7%9E%E4%B8%80%E5%BA%97" in response.headers["content-disposition"]
