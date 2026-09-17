from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event

from domain.inventory_schema import PURCHASE_PRINT_TEMPLATE_TABLE
from storage.inventory_repository import InventoryRepository


def _repository() -> tuple[InventoryRepository, object]:
    engine = create_engine("sqlite://")
    event.listen(
        engine,
        "connect",
        lambda connection, _record: connection.create_function(
            "date_trunc", 2, lambda _unit, value: value
        ),
    )
    PURCHASE_PRINT_TEMPLATE_TABLE.create(engine)
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    return repository, engine


def test_authorized_accounts_read_the_same_shared_template_catalog() -> None:
    repository, engine = _repository()
    with engine.begin() as connection:
        connection.execute(
            PURCHASE_PRINT_TEMPLATE_TABLE.insert().values(
                id=1,
                user_id=0,
                template_key="shared-label",
                template_name="共享标签",
                is_default=True,
                config={"elements": [{"kind": "text", "text": "共享"}]},
                updated_at=datetime.now(timezone.utc),
            )
        )

    first_account = repository.list_purchase_print_templates(1)
    second_account = repository.list_purchase_print_templates(99)

    assert [item["template_key"] for item in first_account] == ["shared-label"]
    assert second_account == first_account
    assert repository.get_default_purchase_print_template(1) == (
        repository.get_default_purchase_print_template(99)
    )


def test_account_id_cannot_select_a_private_template_scope() -> None:
    repository, engine = _repository()
    with engine.begin() as connection:
        connection.execute(
            PURCHASE_PRINT_TEMPLATE_TABLE.insert().values(
                id=1,
                user_id=8,
                template_key="old-private-label",
                template_name="旧个人标签",
                is_default=True,
                config={"elements": [{"kind": "text", "text": "个人"}]},
            )
        )

    assert repository.list_purchase_print_templates(8) == []
    assert repository.list_purchase_print_templates(20) == []
