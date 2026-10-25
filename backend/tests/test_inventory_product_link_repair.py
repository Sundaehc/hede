from copy import deepcopy
from decimal import Decimal

import pytest

from scripts.repair_inventory_product_links import assert_identity_only, repair_candidate, write_unresolved


def candidate_row():
    return {
        "issue_type": "inactive_identity", "document_brand": "ns", "linked_brand": "ns",
        "product_code": "SKU-1", "candidate_count": 1,
        "candidates": [{"id": 11, "sku": "SKU-1", "brand": "ns"}],
    }


@pytest.mark.parametrize("issue_type", ["unlinked", "inactive_identity"])
def test_repairs_only_unique_exact_same_brand_candidates(issue_type):
    row = candidate_row()
    row["issue_type"] = issue_type
    assert repair_candidate(row) == row["candidates"][0]


@pytest.mark.parametrize("change", [
    {"issue_type": "brand_mismatch"}, {"candidate_count": 2}, {"candidates": []},
    {"document_brand": "other"}, {"linked_brand": "other"}, {"product_code": "STYLE"},
    {"candidates": [{"id": 11, "sku": "SKU-1", "brand": "other"}]},
])
def test_rejects_ambiguous_cross_brand_or_renamed_code(change):
    assert repair_candidate({**candidate_row(), **change}) is None


def test_identity_only_verification_keeps_business_fields():
    before = {"id": 1, "product_identity_id": 2, "quantity": Decimal("60"), "unit_price": Decimal("268"),
              "amount": Decimal("16080"), "product_code": "SKU-1", "size_quantities": {"230": "60"}, "updated_at": "old"}
    assert_identity_only(before, {**before, "product_identity_id": 11, "updated_at": "new"}, 11)
    for field, value in {"unit_price": 250.6, "amount": 15036, "product_code": "NEW", "quantity": 59, "size_quantities": {}}.items():
        with pytest.raises(ValueError, match="Unexpected business-field"):
            assert_identity_only(before, {**deepcopy(before), "product_identity_id": 11, field: value}, 11)


def test_unresolved_export_preserves_every_row_and_reason(tmp_path):
    row = {"detail_id": 1, "document_number": "DOC", "document_type": "进货单", "document_brand": "ns",
           "product_code": "SKU", "product_name": "测试", "unit_price": "268", "amount": "16080",
           "reason": "无对应有效档案", "other_brand_candidates": []}
    output = tmp_path / "unresolved.csv"
    write_unresolved(output, [row, {**row, "detail_id": 2}])
    lines = output.read_text(encoding="utf-8-sig").splitlines()
    assert len(lines) == 3
    assert "未修复原因" in lines[0]
    assert all("无对应有效档案" in line for line in lines[1:])
