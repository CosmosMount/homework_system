"""Add internal material ledger and immutable loan history."""

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0031"
down_revision: str | None = "20261003_0030"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("qr_token", sa.Uuid(), nullable=False, unique=True),
        sa.Column("registration_key", sa.Uuid(), nullable=False, unique=True),
        sa.Column("registration_request_hash", sa.String(64), nullable=False),
        sa.Column("registration_count", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("tech_group", sa.String(32), nullable=False),
        sa.Column("pair_key", sa.Uuid()),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="name_present"),
        sa.CheckConstraint("price >= 0 AND price <= 9999999999.99", name="price_range"),
        sa.CheckConstraint("registration_count BETWEEN 1 AND 200", name="registration_count_range"),
        sa.CheckConstraint(
            "registration_request_hash ~ '^[0-9a-f]{64}$'", name="registration_hash_format"
        ),
        sa.CheckConstraint(
            "tech_group IN ('机械', '硬件', '电控', '算法', '宣运', '通用')",
            name="tech_group_allowed",
        ),
    )
    op.create_index("ix_materials_tech_group_created", "materials", ["tech_group", "created_at"])
    op.create_index("ix_materials_pair_key", "materials", ["pair_key"])
    op.create_index("ix_materials_visible_updated", "materials", ["deleted_at", "updated_at"])
    op.create_table(
        "material_loans",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey("materials.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("borrower_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("checkout_idempotency_key", sa.Uuid(), nullable=False, unique=True),
        sa.Column("return_idempotency_key", sa.Uuid(), unique=True),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column("photo_object_key", sa.String(500)),
        sa.Column("photo_mime_type", sa.String(50)),
        sa.Column("photo_size", sa.Integer()),
        sa.Column("photo_sha256", sa.String(64)),
        sa.Column("photo_cleared_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(returned_at IS NULL AND return_idempotency_key IS NULL AND "
            "photo_object_key IS NULL AND photo_cleared_at IS NULL) OR "
            "(returned_at IS NOT NULL AND return_idempotency_key IS NOT NULL AND "
            "((photo_object_key IS NOT NULL AND photo_cleared_at IS NULL) OR "
            "(photo_object_key IS NULL AND photo_cleared_at IS NOT NULL)))",
            name="return_photo_lifecycle",
        ),
        sa.CheckConstraint(
            "returned_at IS NULL OR returned_at >= checked_out_at", name="return_time"
        ),
        sa.CheckConstraint(
            "(photo_object_key IS NULL AND photo_mime_type IS NULL AND photo_size IS NULL "
            "AND photo_sha256 IS NULL) OR (photo_object_key IS NOT NULL AND "
            "photo_mime_type IS NOT NULL AND photo_size > 0 AND photo_size <= 8388608 "
            "AND photo_sha256 ~ '^[0-9a-f]{64}$')",
            name="photo_metadata_consistent",
        ),
    )
    op.create_index(
        "uq_material_loans_active_material",
        "material_loans",
        ["material_id"],
        unique=True,
        postgresql_where=sa.text("returned_at IS NULL"),
    )
    op.create_index(
        "ix_material_loans_material_history", "material_loans", ["material_id", "checked_out_at"]
    )
    op.create_index(
        "ix_material_loans_borrower_active", "material_loans", ["borrower_user_id", "returned_at"]
    )
    op.execute("""
    CREATE FUNCTION protect_material_identity() RETURNS trigger AS $$
    BEGIN
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.qr_token IS DISTINCT FROM OLD.qr_token
         OR NEW.registration_key IS DISTINCT FROM OLD.registration_key
         OR NEW.registration_request_hash IS DISTINCT FROM OLD.registration_request_hash
         OR NEW.registration_count IS DISTINCT FROM OLD.registration_count
         OR NEW.pair_key IS DISTINCT FROM OLD.pair_key
         OR NEW.created_at IS DISTINCT FROM OLD.created_at
         OR (NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id AND NOT
             (current_setting('pnx.account_erasure', true) = 'on'
              AND NEW.created_by_user_id IS NULL))
      THEN RAISE EXCEPTION 'material identity is immutable'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER materials_protect_identity BEFORE UPDATE ON materials
      FOR EACH ROW EXECUTE FUNCTION protect_material_identity()
    """)
    op.execute("""
    CREATE FUNCTION protect_material_loan_history() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'material loan history is append-only'; END IF;
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.material_id IS DISTINCT FROM OLD.material_id
         OR NEW.checkout_idempotency_key IS DISTINCT FROM OLD.checkout_idempotency_key
         OR NEW.checked_out_at IS DISTINCT FROM OLD.checked_out_at
      THEN RAISE EXCEPTION 'material loan identity is immutable'; END IF;
      IF NEW.borrower_user_id IS DISTINCT FROM OLD.borrower_user_id THEN
        IF current_setting('pnx.account_erasure', true) IS DISTINCT FROM 'on'
           OR NEW.borrower_user_id IS NOT NULL
           OR NEW.returned_at IS DISTINCT FROM OLD.returned_at
           OR NEW.return_idempotency_key IS DISTINCT FROM OLD.return_idempotency_key
           OR NEW.photo_object_key IS DISTINCT FROM OLD.photo_object_key
           OR NEW.photo_cleared_at IS DISTINCT FROM OLD.photo_cleared_at
        THEN RAISE EXCEPTION 'material borrower is immutable'; END IF;
        RETURN NEW;
      END IF;
      IF OLD.returned_at IS NULL THEN
        IF NEW.returned_at IS NULL OR NEW.return_idempotency_key IS NULL
           OR NEW.photo_object_key IS NULL OR NEW.photo_cleared_at IS NOT NULL
        THEN RAISE EXCEPTION 'material return requires photo'; END IF;
      ELSIF OLD.photo_object_key IS NOT NULL
         AND NEW.returned_at IS NOT DISTINCT FROM OLD.returned_at
         AND NEW.return_idempotency_key IS NOT DISTINCT FROM OLD.return_idempotency_key
         AND NEW.photo_object_key IS NULL AND NEW.photo_mime_type IS NULL
         AND NEW.photo_size IS NULL AND NEW.photo_sha256 IS NULL
         AND NEW.photo_cleared_at IS NOT NULL AND OLD.photo_cleared_at IS NULL
      THEN RETURN NEW;
      ELSE RAISE EXCEPTION 'material loan history is immutable'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER material_loans_protect_history BEFORE UPDATE OR DELETE ON material_loans
      FOR EACH ROW EXECUTE FUNCTION protect_material_loan_history()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER material_loans_protect_history ON material_loans")
    op.execute("DROP FUNCTION protect_material_loan_history()")
    op.execute("DROP TRIGGER materials_protect_identity ON materials")
    op.execute("DROP FUNCTION protect_material_identity()")
    op.drop_table("material_loans")
    op.drop_table("materials")
