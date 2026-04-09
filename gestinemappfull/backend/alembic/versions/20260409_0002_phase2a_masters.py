"""phase2a masters third parties company accounts

Revision ID: 20260409_0002
Revises: 20260409_0001
Create Date: 2026-04-09 13:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0002"
down_revision = "20260409_0001"
branch_labels = None
depends_on = None


third_party_type = sa.Enum("client", "supplier", "both", "bank", "other", name="third_party_type")
account_type = sa.Enum("client", "supplier", "bank", "expense", "income", "tax", "other", name="account_type")
account_source = sa.Enum("manual_app", "a3_import", "excel_import", name="account_source")
account_sync_status = sa.Enum(
    "not_synced",
    "synced",
    "pending_sync",
    "sync_error",
    name="account_sync_status",
)


def upgrade() -> None:
    third_party_type.create(op.get_bind(), checkfirst=True)
    account_type.create(op.get_bind(), checkfirst=True)
    account_source.create(op.get_bind(), checkfirst=True)
    account_sync_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "global_third_parties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("third_party_type", third_party_type, nullable=False),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("trade_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_global_third_parties_tax_id", "global_third_parties", ["tax_id"], unique=False)
    op.create_index("ix_global_third_parties_legal_name", "global_third_parties", ["legal_name"], unique=False)
    op.create_index(
        "ix_global_third_parties_third_party_type",
        "global_third_parties",
        ["third_party_type"],
        unique=False,
    )

    op.create_table(
        "company_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_type", account_type, nullable=False),
        sa.Column("global_third_party_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("source", account_source, nullable=False, server_default="manual_app"),
        sa.Column("sync_status", account_sync_status, nullable=False, server_default="not_synced"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["global_third_party_id"], ["global_third_parties.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "account_code", name="uq_company_accounts_company_code"),
    )
    op.create_index("ix_company_accounts_company_id", "company_accounts", ["company_id"], unique=False)
    op.create_index("ix_company_accounts_account_code", "company_accounts", ["account_code"], unique=False)
    op.create_index("ix_company_accounts_name", "company_accounts", ["name"], unique=False)
    op.create_index("ix_company_accounts_account_type", "company_accounts", ["account_type"], unique=False)
    op.create_index("ix_company_accounts_tax_id", "company_accounts", ["tax_id"], unique=False)
    op.create_index(
        "ix_company_accounts_global_third_party_id",
        "company_accounts",
        ["global_third_party_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_company_accounts_global_third_party_id", table_name="company_accounts")
    op.drop_index("ix_company_accounts_tax_id", table_name="company_accounts")
    op.drop_index("ix_company_accounts_account_type", table_name="company_accounts")
    op.drop_index("ix_company_accounts_name", table_name="company_accounts")
    op.drop_index("ix_company_accounts_account_code", table_name="company_accounts")
    op.drop_index("ix_company_accounts_company_id", table_name="company_accounts")
    op.drop_table("company_accounts")

    op.drop_index("ix_global_third_parties_third_party_type", table_name="global_third_parties")
    op.drop_index("ix_global_third_parties_legal_name", table_name="global_third_parties")
    op.drop_index("ix_global_third_parties_tax_id", table_name="global_third_parties")
    op.drop_table("global_third_parties")

    account_sync_status.drop(op.get_bind(), checkfirst=True)
    account_source.drop(op.get_bind(), checkfirst=True)
    account_type.drop(op.get_bind(), checkfirst=True)
    third_party_type.drop(op.get_bind(), checkfirst=True)
