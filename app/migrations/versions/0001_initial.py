"""Initial schema."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=64)),
        sa.Column("full_name", sa.String(length=255)),
        sa.Column("phone_last4", sa.String(length=4)),
        sa.Column("phone_sha256", sa.String(length=255)),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True)),
        sa.Column("dm_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locale", sa.String(length=8)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "chats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255)),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Sofia"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chats_chat_id", "chats", ["chat_id"], unique=True)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE")),
        sa.Column("morning_start", sa.Time(), nullable=False),
        sa.Column("morning_end", sa.Time(), nullable=False),
        sa.Column("evening_start", sa.Time(), nullable=False),
        sa.Column("evening_end", sa.Time(), nullable=False),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_weekends", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Sofia"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("OPERATOR", "MANAGER", name="roleenum"), nullable=False, server_default="OPERATOR"),
        sa.Column("authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authorized_via", sa.Enum("PHONE", "CAPTCHA", "INVITE", name="authorizationmethod")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "chat_id", name="uq_membership_user_chat"),
    )

    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Enum("MORNING", "EVENING", name="checkintype"), nullable=False),
        sa.Column("photo_file_id", sa.String(length=255), nullable=False),
        sa.Column("file_unique_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("checkin_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("user_id", "chat_id", "type", "checkin_date", name="uq_checkins_user_chat_type_date"),
    )

    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("morning_cnt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evening_cnt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_operators", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("misses", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_stats")
    op.drop_table("checkins")
    op.drop_table("memberships")
    op.drop_table("settings")
    op.drop_table("chats")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS roleenum")
    op.execute("DROP TYPE IF EXISTS authorizationmethod")
    op.execute("DROP TYPE IF EXISTS checkintype")
