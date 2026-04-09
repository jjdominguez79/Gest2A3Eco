"""phase3 invoice review base

Revision ID: 20260409_0005
Revises: 20260409_0004
Create Date: 2026-04-09 20:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0005"
down_revision = "20260409_0004"
branch_labels = None
depends_on = None


invoice_review_status = sa.Enum(
    "pending",
    "reviewed",
    "confirmed",
    "error",
    name="invoice_review_status",
)


def upgrade() -> None:
    invoice_review_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "invoice_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_third_party_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_company_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_name_detected", sa.String(length=255), nullable=True),
        sa.Column("supplier_tax_id_detected", sa.String(length=64), nullable=True),
        sa.Column("invoice_number", sa.String(length=128), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("taxable_base", sa.Numeric(14, 2), nullable=True),
        sa.Column("tax_rate", sa.Numeric(7, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("concept", sa.Text(), nullable=True),
        sa.Column("review_status", invoice_review_status, nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_third_party_id"], ["global_third_parties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_company_account_id"], ["company_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
    )
    op.create_index("ix_invoice_reviews_document_id", "invoice_reviews", ["document_id"], unique=True)
    op.create_index("ix_invoice_reviews_review_status", "invoice_reviews", ["review_status"], unique=False)
    op.create_index("ix_invoice_reviews_supplier_third_party_id", "invoice_reviews", ["supplier_third_party_id"], unique=False)
    op.create_index("ix_invoice_reviews_supplier_company_account_id", "invoice_reviews", ["supplier_company_account_id"], unique=False)
    op.create_index("ix_invoice_reviews_reviewed_by_user_id", "invoice_reviews", ["reviewed_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invoice_reviews_reviewed_by_user_id", table_name="invoice_reviews")
    op.drop_index("ix_invoice_reviews_supplier_company_account_id", table_name="invoice_reviews")
    op.drop_index("ix_invoice_reviews_supplier_third_party_id", table_name="invoice_reviews")
    op.drop_index("ix_invoice_reviews_review_status", table_name="invoice_reviews")
    op.drop_index("ix_invoice_reviews_document_id", table_name="invoice_reviews")
    op.drop_table("invoice_reviews")
    invoice_review_status.drop(op.get_bind(), checkfirst=True)
