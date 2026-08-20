from __future__ import annotations

from storage.inventory_repository import InventoryRepository


def _create_detail(
    repository: InventoryRepository,
    *,
    document_type: str,
    product_name: str,
) -> dict[str, object]:
    record = repository.create_record({
        "date": "2026-08-20",
        "document_type": document_type,
        "summary": f"科目改名测试-{document_type}-{product_name}",
    })
    return repository.create_detail({
        "document_id": record["id"],
        "product_name": product_name,
        "amount": "100",
    })


def test_account_subject_rename_syncs_only_exact_accounting_details(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
    previous_name = "测试旧科目"
    current_name = "测试新科目"
    subject = repository.create_account_subject({"name": previous_name})

    accounting_detail = _create_detail(
        repository,
        document_type="应付款增加",
        product_name=previous_name,
    )
    whitespace_detail = _create_detail(
        repository,
        document_type="应收款减少",
        product_name=f" {previous_name} ",
    )
    product_detail = _create_detail(
        repository,
        document_type="进货单",
        product_name=previous_name,
    )
    partial_match_detail = _create_detail(
        repository,
        document_type="应付款减少",
        product_name=f"{previous_name}-其他",
    )

    updated, synced_detail_count = repository.update_account_subject(
        int(subject["id"]),
        {"name": current_name},
    )

    assert updated is not None
    assert updated["name"] == current_name
    assert synced_detail_count == 2
    assert repository.get_detail(int(accounting_detail["id"]))["product_name"] == current_name
    assert repository.get_detail(int(whitespace_detail["id"]))["product_name"] == current_name
    assert repository.get_detail(int(product_detail["id"]))["product_name"] == previous_name
    assert repository.get_detail(int(partial_match_detail["id"]))["product_name"] == f"{previous_name}-其他"
