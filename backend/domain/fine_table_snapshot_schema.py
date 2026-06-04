from __future__ import annotations

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Identity, Index, Integer, JSON, Table, Text, UniqueConstraint, func

from domain.schema import METADATA


FINE_TABLE_SNAPSHOT_BATCH_TABLE = Table(
    "fine_table_snapshot_batches",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("snapshot_date", Date, nullable=False),
    Column("total_rows", Integer, nullable=False, default=0),
    Column("latest_order_date", Date, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.date_trunc("minute", func.now()),
        onupdate=func.date_trunc("minute", func.now()),
    ),
    UniqueConstraint("brand", "snapshot_date", name="uq_fine_table_snapshot_batches_brand_date"),
)


FINE_TABLE_SNAPSHOT_ROW_TABLE = Table(
    "fine_table_snapshot_rows",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column(
        "batch_id",
        BigInteger,
        ForeignKey("fine_table_snapshot_batches.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("sku", Text, nullable=True),
    Column("original_sku", Text, nullable=True),
    Column("row_index", Integer, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.date_trunc("minute", func.now())),
    UniqueConstraint("batch_id", "row_index", name="uq_fine_table_snapshot_rows_batch_row_index"),
)

Index("idx_fine_table_snapshot_batches_brand_date", FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.brand, FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.snapshot_date)
Index("idx_fine_table_snapshot_rows_batch", FINE_TABLE_SNAPSHOT_ROW_TABLE.c.batch_id)
Index("idx_fine_table_snapshot_rows_batch_row_index", FINE_TABLE_SNAPSHOT_ROW_TABLE.c.batch_id, FINE_TABLE_SNAPSHOT_ROW_TABLE.c.row_index)
Index("idx_fine_table_snapshot_rows_batch_sku", FINE_TABLE_SNAPSHOT_ROW_TABLE.c.batch_id, FINE_TABLE_SNAPSHOT_ROW_TABLE.c.sku)
Index("idx_fine_table_snapshot_rows_batch_original_sku", FINE_TABLE_SNAPSHOT_ROW_TABLE.c.batch_id, FINE_TABLE_SNAPSHOT_ROW_TABLE.c.original_sku)
