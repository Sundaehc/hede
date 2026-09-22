from sqlalchemy import BigInteger, CheckConstraint, Column, Date, DateTime, Index, Integer, JSON, MetaData, Table, Text, UniqueConstraint, func


METADATA = MetaData()
PRODUCT_COPYWRITING_TABLE = Table(
    "product_copywriting",
    METADATA,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("brand", Text, nullable=False),
    Column("source_product_id", BigInteger, nullable=False),
    Column("sku", Text, nullable=False),
    Column("launch_date", Date, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("content", Text),
    Column("source_facts", JSON, nullable=False),
    Column("source_hash", Text, nullable=False),
    Column("source_updated_at", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("endpoint", Text, nullable=False),
    Column("template_version", Text, nullable=False),
    Column("input_prompt", Text),
    Column("system_prompt", Text),
    Column("input_image", JSON),
    Column("previous_result", JSON),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("claim_token", Text),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("error_status", Integer),
    Column("generated_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("brand", "source_product_id", name="uq_product_copywriting_product"),
    CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name="ck_product_copywriting_status"),
    CheckConstraint("status <> 'completed' OR (content IS NOT NULL AND length(content) > 0 AND generated_at IS NOT NULL)", name="ck_product_copywriting_completed"),
)
Index("idx_product_copywriting_launch_status", PRODUCT_COPYWRITING_TABLE.c.launch_date, PRODUCT_COPYWRITING_TABLE.c.status)

PRODUCT_COPYWRITING_HISTORY_TABLE = Table(
    "product_copywriting_history",
    METADATA,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("brand", Text, nullable=False),
    Column("source_product_id", BigInteger, nullable=False),
    Column("snapshot_key", Text, nullable=False),
    Column("generated_at", DateTime(timezone=True), nullable=False),
    Column("model", Text, nullable=False),
    Column("sku", Text, nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("brand", "source_product_id", "snapshot_key", name="uq_product_copywriting_history_snapshot"),
)
Index("idx_product_copywriting_history_product", PRODUCT_COPYWRITING_HISTORY_TABLE.c.brand, PRODUCT_COPYWRITING_HISTORY_TABLE.c.source_product_id, PRODUCT_COPYWRITING_HISTORY_TABLE.c.generated_at, PRODUCT_COPYWRITING_HISTORY_TABLE.c.id)
