"""phase6 a3 settings and accounting traceability

Revision ID: 20260409_0007
Revises: 20260409_0006
Create Date: 2026-04-09 23:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0007"
down_revision = "20260409_0006"
branch_labels = None
depends_on = None


a3_import_mode = sa.Enum(
    "manual",
    "shared_folder",
    "future_connector",
    name="a3_import_mode",
)
new_document_workflow_status = sa.Enum(
    "inbox",
    "classified",
    "pending_review",
    "pending_ocr",
    "pending_accounting",
    "batched",
    "exported",
    "archived",
    "error",
    name="document_workflow_status",
)
old_document_workflow_status = sa.Enum(
    "inbox",
    "classified",
    "pending_review",
    "pending_ocr",
    "pending_accounting",
    "accounted",
    "archived",
    "error",
    name="document_workflow_status_old",
)
new_accounting_batch_status = sa.Enum(
    "draft",
    "generated",
    "downloaded",
    "exported",
    "error",
    name="accounting_batch_status",
)
old_accounting_batch_status = sa.Enum(
    "draft",
    "generated",
    "exported",
    "error",
    name="accounting_batch_status_old",
)


def upgrade() -> None:
    bind = op.get_bind()
    a3_import_mode.create(bind, checkfirst=True)

    op.add_column("companies", sa.Column("a3_company_code", sa.String(length=5), nullable=True))
    op.add_column("companies", sa.Column("a3_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("companies", sa.Column("a3_export_path", sa.String(length=1024), nullable=True))
    op.add_column("companies", sa.Column("a3_import_mode", a3_import_mode, nullable=True))
    op.add_column(
        "companies",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_companies_a3_company_code", "companies", ["a3_company_code"], unique=True)

    op.alter_column("accounting_batches", "filename", new_column_name="file_name")
    op.add_column("accounting_batches", sa.Column("a3_company_code_snapshot", sa.String(length=5), nullable=True))
    op.add_column("accounting_batches", sa.Column("file_hash", sa.String(length=64), nullable=True))
    op.add_column("accounting_batches", sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("accounting_batches", sa.Column("downloaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("accounting_batches", sa.Column("exported_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("accounting_batches", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounting_batches", sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounting_batches", sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("accounting_batches", sa.Column("total_entries", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("accounting_batches", sa.Column("notes", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_accounting_batches_generated_by_user_id",
        "accounting_batches",
        "users",
        ["generated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_accounting_batches_downloaded_by_user_id",
        "accounting_batches",
        "users",
        ["downloaded_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_accounting_batches_exported_by_user_id",
        "accounting_batches",
        "users",
        ["exported_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_accounting_batches_a3_company_code_snapshot", "accounting_batches", ["a3_company_code_snapshot"], unique=False)
    op.create_index("ix_accounting_batches_file_hash", "accounting_batches", ["file_hash"], unique=False)
    op.create_index("ix_accounting_batches_generated_by_user_id", "accounting_batches", ["generated_by_user_id"], unique=False)
    op.create_index("ix_accounting_batches_downloaded_by_user_id", "accounting_batches", ["downloaded_by_user_id"], unique=False)
    op.create_index("ix_accounting_batches_exported_by_user_id", "accounting_batches", ["exported_by_user_id"], unique=False)

    op.execute(
        """
        UPDATE accounting_batches
        SET generated_at = created_at,
            generated_by_user_id = created_by_user_id
        WHERE status IN ('generated', 'exported')
        """
    )
    op.execute(
        """
        UPDATE accounting_batches
        SET downloaded_at = exported_at
        WHERE status = 'exported'
        """
    )
    op.execute(
        """
        UPDATE accounting_batches ab
        SET total_documents = counts.documents_count,
            total_entries = counts.documents_count * 2
        FROM (
            SELECT batch_id, COUNT(*) AS documents_count
            FROM accounting_batch_items
            GROUP BY batch_id
        ) counts
        WHERE counts.batch_id = ab.id
        """
    )
    op.execute(
        """
        UPDATE accounting_batches ab
        SET a3_company_code_snapshot = COALESCE(
            c.a3_company_code,
            CASE
                WHEN REGEXP_REPLACE(c.id::text, '[^0-9]', '', 'g') <> '' THEN LPAD(SUBSTRING(REGEXP_REPLACE(c.id::text, '[^0-9]', '', 'g') FROM 1 FOR 5), 5, '0')
                ELSE '00001'
            END
        )
        FROM companies c
        WHERE c.id = ab.company_id
        """
    )

    op.create_unique_constraint(
        "uq_accounting_batch_items_batch_document",
        "accounting_batch_items",
        ["batch_id", "document_id"],
    )

    op.execute("ALTER TABLE accounting_batches ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE accounting_batches ALTER COLUMN status TYPE text USING status::text")
    op.execute("UPDATE accounting_batches SET status = 'downloaded' WHERE status = 'exported'")
    op.execute("ALTER TYPE accounting_batch_status RENAME TO accounting_batch_status_old")
    new_accounting_batch_status.create(bind, checkfirst=False)
    op.execute(
        """
        ALTER TABLE accounting_batches
        ALTER COLUMN status TYPE accounting_batch_status
        USING status::accounting_batch_status
        """
    )
    op.execute("ALTER TABLE accounting_batches ALTER COLUMN status SET DEFAULT 'draft'")
    old_accounting_batch_status.drop(bind, checkfirst=False)

    op.execute("ALTER TABLE documents ALTER COLUMN workflow_status DROP DEFAULT")
    op.execute("ALTER TABLE documents ALTER COLUMN workflow_status TYPE text USING workflow_status::text")
    op.execute(
        """
        UPDATE documents d
        SET workflow_status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM accounting_batch_items abi
                JOIN accounting_batches ab ON ab.id = abi.batch_id
                WHERE abi.document_id = d.id
                  AND ab.exported_at IS NOT NULL
            ) THEN 'exported'
            WHEN EXISTS (
                SELECT 1
                FROM accounting_batch_items abi
                WHERE abi.document_id = d.id
            ) THEN 'batched'
            ELSE 'batched'
        END
        WHERE d.workflow_status = 'accounted'
        """
    )
    op.execute("ALTER TYPE document_workflow_status RENAME TO document_workflow_status_old")
    new_document_workflow_status.create(bind, checkfirst=False)
    op.execute(
        """
        ALTER TABLE documents
        ALTER COLUMN workflow_status TYPE document_workflow_status
        USING workflow_status::document_workflow_status
        """
    )
    op.execute("ALTER TABLE documents ALTER COLUMN workflow_status SET DEFAULT 'inbox'")
    old_document_workflow_status.drop(bind, checkfirst=False)

    op.alter_column("companies", "a3_enabled", server_default=None)
    op.alter_column("accounting_batches", "total_documents", server_default=None)
    op.alter_column("accounting_batches", "total_entries", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()

    legacy_document_workflow_status = sa.Enum(
        "inbox",
        "classified",
        "pending_review",
        "pending_ocr",
        "pending_accounting",
        "accounted",
        "archived",
        "error",
        name="document_workflow_status",
    )
    legacy_document_workflow_status_old = sa.Enum(
        "inbox",
        "classified",
        "pending_review",
        "pending_ocr",
        "pending_accounting",
        "batched",
        "exported",
        "archived",
        "error",
        name="document_workflow_status_old",
    )
    legacy_accounting_batch_status = sa.Enum(
        "draft",
        "generated",
        "exported",
        "error",
        name="accounting_batch_status",
    )
    legacy_accounting_batch_status_old = sa.Enum(
        "draft",
        "generated",
        "downloaded",
        "exported",
        "error",
        name="accounting_batch_status_old",
    )

    op.execute("ALTER TABLE documents ALTER COLUMN workflow_status DROP DEFAULT")
    op.execute("ALTER TABLE documents ALTER COLUMN workflow_status TYPE text USING workflow_status::text")
    op.execute("UPDATE documents SET workflow_status = 'accounted' WHERE workflow_status IN ('batched', 'exported')")
    op.execute("ALTER TYPE document_workflow_status RENAME TO document_workflow_status_old")
    legacy_document_workflow_status.create(bind, checkfirst=False)
    op.execute(
        """
        ALTER TABLE documents
        ALTER COLUMN workflow_status TYPE document_workflow_status
        USING workflow_status::document_workflow_status
        """
    )
    op.execute("ALTER TABLE documents ALTER COLUMN workflow_status SET DEFAULT 'inbox'")
    legacy_document_workflow_status_old.drop(bind, checkfirst=False)

    op.execute("ALTER TABLE accounting_batches ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE accounting_batches ALTER COLUMN status TYPE text USING status::text")
    op.execute("UPDATE accounting_batches SET status = 'exported' WHERE status IN ('downloaded', 'exported')")
    op.execute("ALTER TYPE accounting_batch_status RENAME TO accounting_batch_status_old")
    legacy_accounting_batch_status.create(bind, checkfirst=False)
    op.execute(
        """
        ALTER TABLE accounting_batches
        ALTER COLUMN status TYPE accounting_batch_status
        USING status::accounting_batch_status
        """
    )
    op.execute("ALTER TABLE accounting_batches ALTER COLUMN status SET DEFAULT 'draft'")
    legacy_accounting_batch_status_old.drop(bind, checkfirst=False)

    op.drop_constraint("uq_accounting_batch_items_batch_document", "accounting_batch_items", type_="unique")

    op.drop_index("ix_accounting_batches_exported_by_user_id", table_name="accounting_batches")
    op.drop_index("ix_accounting_batches_downloaded_by_user_id", table_name="accounting_batches")
    op.drop_index("ix_accounting_batches_generated_by_user_id", table_name="accounting_batches")
    op.drop_index("ix_accounting_batches_file_hash", table_name="accounting_batches")
    op.drop_index("ix_accounting_batches_a3_company_code_snapshot", table_name="accounting_batches")
    op.drop_constraint("fk_accounting_batches_exported_by_user_id", "accounting_batches", type_="foreignkey")
    op.drop_constraint("fk_accounting_batches_downloaded_by_user_id", "accounting_batches", type_="foreignkey")
    op.drop_constraint("fk_accounting_batches_generated_by_user_id", "accounting_batches", type_="foreignkey")
    op.drop_column("accounting_batches", "notes")
    op.drop_column("accounting_batches", "total_entries")
    op.drop_column("accounting_batches", "total_documents")
    op.drop_column("accounting_batches", "downloaded_at")
    op.drop_column("accounting_batches", "generated_at")
    op.drop_column("accounting_batches", "exported_by_user_id")
    op.drop_column("accounting_batches", "downloaded_by_user_id")
    op.drop_column("accounting_batches", "generated_by_user_id")
    op.drop_column("accounting_batches", "file_hash")
    op.drop_column("accounting_batches", "a3_company_code_snapshot")
    op.alter_column("accounting_batches", "file_name", new_column_name="filename")

    op.drop_index("ix_companies_a3_company_code", table_name="companies")
    op.drop_column("companies", "updated_at")
    op.drop_column("companies", "a3_import_mode")
    op.drop_column("companies", "a3_export_path")
    op.drop_column("companies", "a3_enabled")
    op.drop_column("companies", "a3_company_code")
    a3_import_mode.drop(bind, checkfirst=True)
