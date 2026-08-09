"""Add tenant accounts and single-tenant identities.

Revision ID: 20260809_01
Revises:
Create Date: 2026-08-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260809_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("tenant_account"):
        op.create_table(
            "tenant_account",
            sa.Column("id", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("data_source", sa.String(length=32), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("webhook_secret_digest", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tenant_account_is_active", "tenant_account", ["is_active"])

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("user_identity"):
        op.create_table(
            "user_identity",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=120), nullable=False),
            sa.Column("username_normalized", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("account_id", sa.String(length=80), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["tenant_account.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_identity_is_active", "user_identity", ["is_active"])
        op.create_index("ix_user_identity_account_id", "user_identity", ["account_id"])
        op.create_index(
            "ix_user_identity_username_normalized",
            "user_identity",
            ["username_normalized"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in ("user_identity", "tenant_account"):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
