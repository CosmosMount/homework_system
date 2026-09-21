"""Allow account-erasure FK de-identification without weakening version immutability."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260921_0027"
down_revision: str | None = "20260916_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pnx_reject_submission_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            erasure_user_id text := current_setting('pnx.account_erasure_user_id', true);
        BEGIN
            IF current_setting('pnx.account_erasure', true) = 'on'
                AND erasure_user_id IS NOT NULL
                AND erasure_user_id <> ''
            THEN
                IF TG_OP = 'UPDATE' THEN
                    IF OLD.submitted_by::text = erasure_user_id
                        AND NEW.submitted_by IS NULL
                        AND (to_jsonb(NEW) - 'submitted_by') =
                            (to_jsonb(OLD) - 'submitted_by')
                    THEN
                        RETURN NEW;
                    END IF;
                ELSIF TG_OP = 'DELETE' THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM submissions WHERE id = OLD.submission_id
                    ) OR EXISTS (
                        SELECT 1 FROM submissions
                        WHERE id = OLD.submission_id
                            AND assignment_id IS NOT NULL
                            AND owner_user_id::text = erasure_user_id
                    ) THEN
                        RETURN OLD;
                    END IF;
                END IF;
            END IF;
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = 'submission versions are immutable';
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pnx_reject_submission_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                AND current_setting('pnx.account_erasure', true) = 'on'
                AND NOT EXISTS (
                    SELECT 1 FROM submissions WHERE id = OLD.submission_id
                )
            THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = 'submission versions are immutable';
        END;
        $$;
        """
    )
