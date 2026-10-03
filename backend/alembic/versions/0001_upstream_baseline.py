"""Frozen schema produced by upstream commit a41a005.

Revision ID: 0001_upstream
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_upstream"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    now = sa.text("CURRENT_TIMESTAMP")
    op.create_table(
        "users", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String()), sa.Column("username", sa.String()),
        sa.Column("hashed_password", sa.String()), sa.Column("full_name", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "teams", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String()), sa.Column("description", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_teams_id", "teams", ["id"])
    op.create_index("ix_teams_name", "teams", ["name"])
    op.create_table(
        "team_members", sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String()),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=now),
    )
    op.create_table(
        "boards", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String()), sa.Column("description", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id")),
        sa.Column("is_public", sa.Boolean()),
    )
    op.create_index("ix_boards_id", "boards", ["id"])
    op.create_index("ix_boards_name", "boards", ["name"])
    op.create_table(
        "board_members", sa.Column("board_id", sa.Integer(), sa.ForeignKey("boards.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String()),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=now),
    )
    op.create_table(
        "labels", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String()), sa.Column("color", sa.String()),
    )
    op.create_index("ix_labels_id", "labels", ["id"])
    op.create_index("ix_labels_name", "labels", ["name"])
    op.create_table(
        "tasks", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String()), sa.Column("description", sa.String()),
        sa.Column("status", sa.String()), sa.Column("priority", sa.String()),
        sa.Column("position", sa.Integer()), sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("boards.id")),
        sa.Column("is_archived", sa.Boolean()), sa.Column("checklist", sa.JSON()),
    )
    op.create_index("ix_tasks_id", "tasks", ["id"])
    op.create_index("ix_tasks_title", "tasks", ["title"])
    op.create_table(
        "task_labels", sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id")),
        sa.Column("label_id", sa.Integer(), sa.ForeignKey("labels.id")),
    )
    op.create_table(
        "task_members", sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_table(
        "comments", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_comments_id", "comments", ["id"])
    op.create_table(
        "attachments", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String()), sa.Column("file_path", sa.String()),
        sa.Column("url", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_attachments_id", "attachments", ["id"])


def downgrade():
    for name in (
        "attachments", "comments", "task_members", "task_labels", "tasks", "labels",
        "board_members", "boards", "team_members", "teams", "users",
    ):
        op.drop_table(name)
