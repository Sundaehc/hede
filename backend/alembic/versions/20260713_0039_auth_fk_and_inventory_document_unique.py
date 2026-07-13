"""add auth foreign keys and active document number uniqueness

Revision ID: 20260713_0039
Revises: 20260707_0038
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0039"
down_revision = "20260707_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.auth_sessions') IS NOT NULL
               AND to_regclass('public.auth_users') IS NOT NULL THEN
                DELETE FROM auth_sessions AS s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM auth_users AS u
                    WHERE u.id = s.user_id
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.auth_roles') IS NOT NULL
               AND to_regclass('public.auth_departments') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_auth_roles_department_code'
                      AND conrelid = to_regclass('public.auth_roles')
               ) THEN
                ALTER TABLE auth_roles
                ADD CONSTRAINT fk_auth_roles_department_code
                FOREIGN KEY (department_code)
                REFERENCES auth_departments (code)
                ON UPDATE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.auth_users') IS NOT NULL
               AND to_regclass('public.auth_departments') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_auth_users_department_code'
                      AND conrelid = to_regclass('public.auth_users')
               ) THEN
                ALTER TABLE auth_users
                ADD CONSTRAINT fk_auth_users_department_code
                FOREIGN KEY (department_code)
                REFERENCES auth_departments (code)
                ON UPDATE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.auth_users') IS NOT NULL
               AND to_regclass('public.auth_roles') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_auth_users_role_code'
                      AND conrelid = to_regclass('public.auth_users')
               ) THEN
                ALTER TABLE auth_users
                ADD CONSTRAINT fk_auth_users_role_code
                FOREIGN KEY (role_code)
                REFERENCES auth_roles (code)
                ON UPDATE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.auth_sessions') IS NOT NULL
               AND to_regclass('public.auth_users') IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_auth_sessions_user_id'
                      AND conrelid = to_regclass('public.auth_sessions')
               ) THEN
                ALTER TABLE auth_sessions
                ADD CONSTRAINT fk_auth_sessions_user_id
                FOREIGN KEY (user_id)
                REFERENCES auth_users (id)
                ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS inventory_records ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.inventory_records') IS NOT NULL
               AND EXISTS (
                    SELECT 1
                    FROM inventory_records
                    WHERE deleted_at IS NULL
                      AND NULLIF(BTRIM(document_number), '') IS NOT NULL
                    GROUP BY document_number
                    HAVING COUNT(*) > 1
               ) THEN
                RAISE EXCEPTION 'duplicate active inventory document_number exists';
            END IF;

            IF to_regclass('public.inventory_records') IS NOT NULL
               AND to_regclass('public.uq_inventory_records_active_document_number') IS NULL THEN
                CREATE UNIQUE INDEX uq_inventory_records_active_document_number
                ON inventory_records (document_number)
                WHERE deleted_at IS NULL
                  AND NULLIF(BTRIM(document_number), '') IS NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_inventory_records_active_document_number")
    op.execute("ALTER TABLE IF EXISTS auth_sessions DROP CONSTRAINT IF EXISTS fk_auth_sessions_user_id")
    op.execute("ALTER TABLE IF EXISTS auth_users DROP CONSTRAINT IF EXISTS fk_auth_users_role_code")
    op.execute("ALTER TABLE IF EXISTS auth_users DROP CONSTRAINT IF EXISTS fk_auth_users_department_code")
    op.execute("ALTER TABLE IF EXISTS auth_roles DROP CONSTRAINT IF EXISTS fk_auth_roles_department_code")
