"""phase2b documents base

Revision ID: 20260409_0003
Revises: 20260409_0002
Create Date: 2026-04-09 16:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0003"
down_revision = "20260409_0002"
branch_labels = None
depends_on = None


document_source = sa.Enum("upload", "email", "generated_internal", "imported", name="document_source")
document_type = sa.Enum(
    "invoice_issued",
    "invoice_received",
    "bank_statement",
    "contract",
    "bank_receipt",
    "unassigned",
    "other",
    name="document_type",
)
document_workflow_status = sa.Enum(
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


def upgrade() -> None:
    document_source.create(op.get_bind(), checkfirst=True)
    document_type.create(op.get_bind(), checkfirst=True)
    document_workflow_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("source", document_source, nullable=False, server_default="upload"),
        sa.Column("document_type", document_type, nullable=False, server_default="unassigned"),
        sa.Column("workflow_status", document_workflow_status, nullable=False, server_default="inbox"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"], unique=False)
    op.create_index("ix_documents_original_filename", "documents", ["original_filename"], unique=False)
    op.create_index("ix_documents_sha256_hash", "documents", ["sha256_hash"], unique=False)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], unique=False)
    op.create_index("ix_documents_workflow_status", "documents", ["workflow_status"], unique=False)
    op.create_index("ix_documents_uploaded_by_user_id", "documents", ["uploaded_by_user_id"], unique=False)

    op.create_table(
        "document_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_events_document_id", "document_events", ["document_id"], unique=False)
    op.create_index("ix_document_events_user_id", "document_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_events_user_id", table_name="document_events")
    op.drop_index("ix_document_events_document_id", table_name="document_events")
    op.drop_table("document_events")

    op.drop_index("ix_documents_uploaded_by_user_id", table_name="documents")
    op.drop_index("ix_documents_workflow_status", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_sha256_hash", table_name="documents")
    op.drop_index("ix_documents_original_filename", table_name="documents")
    op.drop_index("ix_documents_company_id", table_name="documents")
    op.drop_table("documents")

    document_workflow_status.drop(op.get_bind(), checkfirst=True)
    document_type.drop(op.get_bind(), checkfirst=True)
    document_source.drop(op.get_bind(), checkfirst=True)
