"""phase1 core auth companies memberships

Revision ID: 20260409_0001
Revises:
Create Date: 2026-04-09 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0001"
down_revision = None
branch_labels = None
depends_on = None


company_role = sa.Enum("admin", "employee", "client", name="company_role")


def upgrade() -> None:
    company_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("cif", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=False)
    op.create_index("ix_companies_cif", "companies", ["cif"], unique=False)

    op.create_table(
        "company_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", company_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "company_id", name="uq_company_memberships_user_company"),
    )
    op.create_index("ix_company_memberships_user_id", "company_memberships", ["user_id"], unique=False)
    op.create_index("ix_company_memberships_company_id", "company_memberships", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_company_memberships_company_id", table_name="company_memberships")
    op.drop_index("ix_company_memberships_user_id", table_name="company_memberships")
    op.drop_table("company_memberships")
    op.drop_index("ix_companies_cif", table_name="companies")
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    company_role.drop(op.get_bind(), checkfirst=True)
