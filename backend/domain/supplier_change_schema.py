from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Identity, Index, Integer, JSON, Table, Text, func

from domain.schema import METADATA


SUPPLIER_CHANGE_TABLE = Table(
    "supplier_change_requests",
    METADATA,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("supplier_id", BigInteger, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("before", JSON, nullable=False),
    Column("proposed", JSON, nullable=False),
    Column("expense_document_count", Integer, nullable=False),
    Column("requester_id", Integer, nullable=False),
    Column("requester_name", Text, nullable=False),
    Column("reviewer_id", Integer),
    Column("reviewer_name", Text),
    Column("review_note", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("reviewed_at", DateTime(timezone=True)),
    CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_supplier_change_status"),
)

_pending = SUPPLIER_CHANGE_TABLE.c.status == "pending"
Index("uq_supplier_change_pending", SUPPLIER_CHANGE_TABLE.c.supplier_id, unique=True,
      postgresql_where=_pending, sqlite_where=_pending)
Index("ix_supplier_change_requests_supplier_status", SUPPLIER_CHANGE_TABLE.c.supplier_id, SUPPLIER_CHANGE_TABLE.c.status)
Index("ix_supplier_change_requests_status_id", SUPPLIER_CHANGE_TABLE.c.status, SUPPLIER_CHANGE_TABLE.c.id)
Index("ix_supplier_change_requests_requester_id", SUPPLIER_CHANGE_TABLE.c.requester_id, SUPPLIER_CHANGE_TABLE.c.id)


class SupplierChangeConflict(ValueError):
    pass


class SupplierNameExists(SupplierChangeConflict):
    def __init__(self, name: str):
        super().__init__(f"供应商“{name}”已存在，请使用不同的供应商全名")
