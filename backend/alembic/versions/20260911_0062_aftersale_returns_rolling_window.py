"""Support rolling-window aftersale history imports.

Revision ID: 20260911_0062
Revises: 20260904_0061
Create Date: 2026-09-11
"""

from alembic import op


revision = "20260911_0062"
down_revision = "20260904_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE jst_aftersale_returns "
        "ADD COLUMN IF NOT EXISTS application_date_value DATE"
    )
    op.execute(
        """
        UPDATE jst_aftersale_returns
        SET application_date_value = to_date(
            split_part(
                replace(
                    coalesce(
                        nullif(raw_payload ->> U&'\\7533\\8BF7\\65E5\\671F', ''),
                        nullif(raw_payload ->> U&'\\767B\\8BB0\\65F6\\95F4', '')
                    ),
                    '/', '-'
                ),
                ' ', 1
            ),
            'YYYY-MM-DD'
        )
        WHERE application_date_value IS NULL
          AND coalesce(
                nullif(raw_payload ->> U&'\\7533\\8BF7\\65E5\\671F', ''),
                nullif(raw_payload ->> U&'\\767B\\8BB0\\65F6\\95F4', '')
              ) ~ '^\\d{4}[/-]\\d{1,2}[/-]\\d{1,2}'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jst_aftersale_returns_application_date
        ON jst_aftersale_returns (application_date_value)
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_jst_aftersale_returns_business_date")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_jst_aftersale_returns_business_date
        ON jst_aftersale_returns (
            COALESCE(application_date_value, order_date_value, order_time_value)
        )
        """
    )
    op.execute("DROP VIEW IF EXISTS v_jst_aftersale_returns_normalized")
    op.execute(
        """
        CREATE VIEW v_jst_aftersale_returns_normalized AS
        SELECT source.*,
               COALESCE(source.application_date_value, source.order_date_value,
                        source.order_time_value) AS business_date
        FROM jst_aftersale_returns AS source
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_jst_aftersale_returns_normalized")
    op.execute(
        """
        CREATE VIEW v_jst_aftersale_returns_normalized AS
        SELECT source.*, source.order_date_value AS business_date
        FROM jst_aftersale_returns AS source
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_jst_aftersale_returns_business_date")
    op.execute("DROP INDEX IF EXISTS idx_jst_aftersale_returns_application_date")
    op.execute("ALTER TABLE jst_aftersale_returns DROP COLUMN IF EXISTS application_date_value")
