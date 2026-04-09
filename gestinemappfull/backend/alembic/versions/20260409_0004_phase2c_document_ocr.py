"""phase2c document ocr base

Revision ID: 20260409_0004
Revises: 20260409_0003
Create Date: 2026-04-09 18:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0004"
down_revision = "20260409_0003"
branch_labels = None
depends_on = None


document_ocr_status = sa.Enum(
    "pending",
    "processed",
    "reviewed",
    "error",
    name="document_ocr_status",
)


def upgrade() -> None:
    document_ocr_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "document_ocr_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", document_ocr_status, nullable=False, server_default="pending"),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
    )
    op.create_index("ix_document_ocr_results_document_id", "document_ocr_results", ["document_id"], unique=True)
    op.create_index("ix_document_ocr_results_status", "document_ocr_results", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_ocr_results_status", table_name="document_ocr_results")
    op.drop_index("ix_document_ocr_results_document_id", table_name="document_ocr_results")
    op.drop_table("document_ocr_results")
    document_ocr_status.drop(op.get_bind(), checkfirst=True)
