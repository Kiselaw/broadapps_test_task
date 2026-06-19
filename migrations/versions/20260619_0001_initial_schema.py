"""initial schema

Revision ID: 20260619_0001
Revises:
Create Date: 2026-06-19 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260619_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_user_id", sa.String(length=36), nullable=False),
        sa.Column("api_key_hash", sa.String(length=128), nullable=False),
        sa.Column("balance_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("callback_url", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_api_key_hash", "users", ["api_key_hash"], unique=False)
    op.create_index(
        "ix_users_external_user_id",
        "users",
        ["external_user_id"],
        unique=True,
    )

    op.create_table(
        "balance_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("CREDIT", "DEBIT", "REFUND", name="transactionkind", native_enum=False),
            nullable=False,
        ),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "media_kind",
            sa.Enum("IMAGE", "VIDEO", name="mediakind", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "input_kind",
            sa.Enum("TEXT", "IMAGE", name="inputkind", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "CREATED",
                "QUEUED",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="generationstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("source_image_url", sa.String(length=1024), nullable=True),
        sa.Column("callback_url", sa.String(length=1024), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column("provider_task_id", sa.String(length=128), nullable=True),
        sa.Column("result_url", sa.String(length=1024), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generation_tasks_status",
        "generation_tasks",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_generation_tasks_user_id",
        "generation_tasks",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_user_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_events_external_user_id",
        "payment_events",
        ["external_user_id"],
        unique=False,
    )

    op.create_table(
        "rate_limit_states",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("requests_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("target_url", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "DELIVERED", "FAILED", name="deliverystatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_deliveries_generation_id",
        "webhook_deliveries",
        ["generation_id"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_deliveries_status",
        "webhook_deliveries",
        ["status"],
        unique=False,
    )

    op.create_table(
        "provider_health",
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("available_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider_name"),
    )


def downgrade() -> None:
    op.drop_table("provider_health")
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_generation_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_table("rate_limit_states")
    op.drop_index("ix_payment_events_external_user_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_generation_tasks_user_id", table_name="generation_tasks")
    op.drop_index("ix_generation_tasks_status", table_name="generation_tasks")
    op.drop_table("generation_tasks")
    op.drop_table("balance_transactions")
    op.drop_index("ix_users_external_user_id", table_name="users")
    op.drop_index("ix_users_api_key_hash", table_name="users")
    op.drop_table("users")
