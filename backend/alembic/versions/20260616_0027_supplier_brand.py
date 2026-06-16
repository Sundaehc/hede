"""add brand to suppliers

Revision ID: 20260616_0027
Revises: 20260616_0026
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op


revision: str = "20260616_0027"
down_revision: str | None = "20260616_0026"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS brand TEXT")
    op.execute(
        """
        DELETE FROM suppliers AS bad
        USING suppliers AS good
        WHERE bad.id <> good.id
          AND bad.name = good.name
          AND good.brand = CASE
              WHEN upper(coalesce(bad.name, '')) LIKE '%TRUMPPIPE%'
                OR coalesce(bad.name, '') LIKE '%烟斗%' THEN 'yandou'
              WHEN upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
                OR coalesce(bad.name, '') LIKE '%伊伴%' THEN 'eblan'
              WHEN upper(coalesce(bad.name, '')) LIKE '%SMILEY%'
                OR coalesce(bad.name, '') LIKE '%笑脸%'
                OR coalesce(bad.name, '') LIKE '%小莲%' THEN 'smiley'
              WHEN coalesce(bad.name, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
              ELSE bad.brand
          END
          AND bad.brand IS DISTINCT FROM good.brand
          AND (
              upper(coalesce(bad.name, '')) LIKE '%TRUMPPIPE%'
              OR coalesce(bad.name, '') LIKE '%烟斗%'
              OR upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
              OR coalesce(bad.name, '') LIKE '%伊伴%'
              OR upper(coalesce(bad.name, '')) LIKE '%SMILEY%'
              OR coalesce(bad.name, '') LIKE '%笑脸%'
              OR coalesce(bad.name, '') LIKE '%小莲%'
              OR coalesce(bad.name, '') LIKE '%千百度女鞋%'
          )
        """
    )
    op.execute(
        """
        UPDATE suppliers
        SET brand = CASE
            WHEN upper(coalesce(name, '')) LIKE '%TRUMPPIPE%'
              OR coalesce(name, '') LIKE '%烟斗%' THEN 'yandou'
            WHEN upper(coalesce(name, '')) LIKE '%EBLAN%'
              OR coalesce(name, '') LIKE '%伊伴%' THEN 'eblan'
            WHEN upper(coalesce(name, '')) LIKE '%SMILEY%'
              OR coalesce(name, '') LIKE '%笑脸%'
              OR coalesce(name, '') LIKE '%小莲%' THEN 'smiley'
            WHEN coalesce(name, '') LIKE '%千百度品牌方%' THEN 'cbanner_mens'
            WHEN coalesce(name, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
            WHEN coalesce(name, '') LIKE '%千百度%' THEN 'cbanner_mens'
            ELSE 'cbanner_mens'
        END
        WHERE brand IS NULL
           OR brand = ''
           OR (
                upper(coalesce(name, '')) LIKE '%TRUMPPIPE%'
                OR coalesce(name, '') LIKE '%烟斗%'
                OR upper(coalesce(name, '')) LIKE '%EBLAN%'
                OR coalesce(name, '') LIKE '%伊伴%'
                OR upper(coalesce(name, '')) LIKE '%SMILEY%'
                OR coalesce(name, '') LIKE '%笑脸%'
                OR coalesce(name, '') LIKE '%小莲%'
                OR coalesce(name, '') LIKE '%千百度女鞋%'
           )
        """
    )
    op.execute("ALTER TABLE IF EXISTS suppliers ALTER COLUMN brand SET NOT NULL")
    op.execute("ALTER TABLE IF EXISTS suppliers DROP CONSTRAINT IF EXISTS uq_supplier_name")
    op.execute("ALTER TABLE IF EXISTS suppliers ADD CONSTRAINT uq_supplier_brand_name UNIQUE (brand, name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_brand ON suppliers (brand)")
    op.execute(
        """
        do $$
        begin
            if to_regclass('public.gj_merged_product_info') is not null then
                insert into suppliers (brand, name)
                select distinct
                    case
                        when upper(coalesce(g.primary_supplier, '')) like '%TRUMPPIPE%'
                          or coalesce(g.primary_supplier, '') like '%烟斗%' then 'yandou'
                        when upper(coalesce(g.primary_supplier, '')) like '%EBLAN%'
                          or coalesce(g.primary_supplier, '') like '%伊伴%' then 'eblan'
                        when upper(coalesce(g.primary_supplier, '')) like '%SMILEY%'
                          or coalesce(g.primary_supplier, '') like '%笑脸%'
                          or coalesce(g.primary_supplier, '') like '%小莲%' then 'smiley'
                        when coalesce(g.primary_supplier, '') like '%千百度女鞋%' then 'cbanner_womens'
                        else g.fine_table_brand
                    end as brand,
                    g.primary_supplier
                from gj_merged_product_info g
                where g.fine_table_brand in ('cbanner_mens', 'cbanner_womens', 'yandou', 'eblan', 'smiley')
                  and coalesce(g.primary_supplier, '') <> ''
                  and not exists (
                      select 1
                      from suppliers s
                      where s.brand = case
                            when upper(coalesce(g.primary_supplier, '')) like '%TRUMPPIPE%'
                              or coalesce(g.primary_supplier, '') like '%烟斗%' then 'yandou'
                            when upper(coalesce(g.primary_supplier, '')) like '%EBLAN%'
                              or coalesce(g.primary_supplier, '') like '%伊伴%' then 'eblan'
                            when upper(coalesce(g.primary_supplier, '')) like '%SMILEY%'
                              or coalesce(g.primary_supplier, '') like '%笑脸%'
                              or coalesce(g.primary_supplier, '') like '%小莲%' then 'smiley'
                            when coalesce(g.primary_supplier, '') like '%千百度女鞋%' then 'cbanner_womens'
                            else g.fine_table_brand
                        end
                        and s.name = g.primary_supplier
                  );
            end if;
        end $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_suppliers_brand")
    op.execute("ALTER TABLE IF EXISTS suppliers DROP CONSTRAINT IF EXISTS uq_supplier_brand_name")
    op.execute("ALTER TABLE IF EXISTS suppliers ADD CONSTRAINT uq_supplier_name UNIQUE (name)")
    op.execute("ALTER TABLE IF EXISTS suppliers DROP COLUMN IF EXISTS brand")
