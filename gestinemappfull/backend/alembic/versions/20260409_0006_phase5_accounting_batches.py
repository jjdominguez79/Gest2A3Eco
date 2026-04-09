"""phase5 accounting batches

Revision ID: 20260409_0006
Revises: 20260409_0005
Create Date: 2026-04-09 22:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0006"
down_revision = "20260409_0005"
branch_labels = None
depends_on = None


accounting_batch_type = sa.Enum(
    "invoice_received",
    name="accounting_batch_type",
)
accounting_batch_status = sa.Enum(
    "draft",
    "generated",
    "exported",
    "error",
    name="accounting_batch_status",
)
accounting_batch_item_status = sa.Enum(
    "included",
    "error",
    name="accounting_batch_item_status",
)


def upgrade() -> None:
    accounting_batch_type.create(op.get_bind(), checkfirst=True)
    accounting_batch_status.create(op.get_bind(), checkfirst=True)
    accounting_batch_item_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "accounting_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_type", accounting_batch_type, nullable=False, server_default="invoice_received"),
        sa.Column("status", accounting_batch_status, nullable=False, server_default="draft"),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounting_batches_company_id", "accounting_batches", ["company_id"], unique=False)
    op.create_index("ix_accounting_batches_status", "accounting_batches", ["status"], unique=False)
    op.create_index("ix_accounting_batches_created_by_user_id", "accounting_batches", ["created_by_user_id"], unique=False)

    op.create_table(
        "accounting_batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", accounting_batch_item_status, nullable=False, server_default="included"),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["accounting_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_review_id"], ["invoice_reviews.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounting_batch_items_batch_id", "accounting_batch_items", ["batch_id"], unique=False)
    op.create_index("ix_accounting_batch_items_document_id", "accounting_batch_items", ["document_id"], unique=False)
    op.create_index("ix_accounting_batch_items_invoice_review_id", "accounting_batch_items", ["invoice_review_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_accounting_batch_items_invoice_review_id", table_name="accounting_batch_items")
    op.drop_index("ix_accounting_batch_items_document_id", table_name="accounting_batch_items")
    op.drop_index("ix_accounting_batch_items_batch_id", table_name="accounting_batch_items")
    op.drop_table("accounting_batch_items")

    op.drop_index("ix_accounting_batches_created_by_user_id", table_name="accounting_batches")
    op.drop_index("ix_accounting_batches_status", table_name="accounting_batches")
    op.drop_index("ix_accounting_batches_company_id", table_name="accounting_batches")
    op.drop_table("accounting_batches")

    accounting_batch_item_status.drop(op.get_bind(), checkfirst=True)
    accounting_batch_status.drop(op.get_bind(), checkfirst=True)
    accounting_batch_type.drop(op.get_bind(), checkfirst=True)
