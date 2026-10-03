"""Data-preserving TeamFlow ownership, ordering and collaboration schema.

Revision ID: 0002_teamflow
Revises: 0001_upstream
"""

from datetime import datetime, timezone
from pathlib import PurePosixPath

from alembic import op
import sqlalchemy as sa

revision = "0002_teamflow"
down_revision = "0001_upstream"
branch_labels = None
depends_on = None
NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def table(name):
    return sa.Table(name, sa.MetaData(), autoload_with=op.get_bind())


def validate_legacy_data():
    connection = op.get_bind()
    users, teams, boards, tasks = (table(name) for name in ("users", "teams", "boards", "tasks"))
    user_ids = set(connection.execute(sa.select(users.c.id)).scalars())
    team_ids = set(connection.execute(sa.select(teams.c.id)).scalars())
    board_ids = set(connection.execute(sa.select(boards.c.id)).scalars())
    for field in ("username", "email"):
        normalized = sa.func.lower(users.c[field])
        duplicate = connection.execute(sa.select(normalized).where(users.c[field].is_not(None))
            .group_by(normalized).having(sa.func.count() > 1)).first()
        if duplicate:
            raise RuntimeError(f"Legacy users have duplicate case-insensitive {field}; resolve accounts before upgrade")
    for team in connection.execute(sa.select(teams)).mappings():
        if team["created_by_id"] not in user_ids:
            raise RuntimeError(f"Legacy team {team['id']} has no valid creator; repair ownership before upgrade")
    for board in connection.execute(sa.select(boards)).mappings():
        if board["team_id"] not in team_ids or board["created_by_id"] not in user_ids:
            raise RuntimeError(f"Legacy board {board['id']} has invalid team/creator; repair before upgrade")
    for task in connection.execute(sa.select(tasks)).mappings():
        if task["board_id"] not in board_ids or task["creator_id"] not in user_ids:
            raise RuntimeError(f"Legacy task {task['id']} has invalid board/creator; repair before upgrade")
    if connection.execute(sa.select(table("labels").c.id).limit(1)).first() and not board_ids:
        raise RuntimeError("Legacy labels have no board to preserve them in; assign a recovery board before upgrade")


def upgrade():
    validate_legacy_data()
    now = sa.text("CURRENT_TIMESTAMP")
    op.add_column("teams", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("teams", sa.Column("membership_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("boards", sa.Column("visibility", sa.String(), nullable=False, server_default="team"))
    op.add_column("boards", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "board_columns", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("boards.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("wip_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.UniqueConstraint("board_id", "position", name="uq_column_position"),
        sa.CheckConstraint("position >= 0", name="ck_column_position_nonnegative"),
        sa.CheckConstraint("wip_limit IS NULL OR wip_limit > 0", name="ck_column_wip"),
    )
    op.add_column("tasks", sa.Column("column_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("assignee_id", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("labels", sa.Column("board_id", sa.Integer(), nullable=True))
    op.add_column("labels", sa.Column("normalized_name", sa.String(), nullable=True))
    for name, kind in (("storage_name", sa.String()), ("original_name", sa.String()),
                       ("content_type", sa.String()), ("size", sa.Integer())):
        op.add_column("attachments", sa.Column(name, kind, nullable=True))

    backfill_ownership_and_columns()
    backfill_labels()
    attachments = table("attachments")
    for row in op.get_bind().execute(sa.select(attachments)).mappings():
        display_name = PurePosixPath((row["filename"] or "attachment").replace("\\", "/")).name
        op.get_bind().execute(sa.update(attachments).where(attachments.c.id == row["id"]).values(
            original_name=display_name, url=f"/api/tasks/{row['task_id']}/attachments/{row['id']}/download",
        ))

    with op.batch_alter_table("teams", naming_convention=NAMING) as batch:
        batch.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_teams_owner_id_users", "users", ["owner_id"], ["id"])
    with op.batch_alter_table("boards", naming_convention=NAMING) as batch:
        batch.create_check_constraint("ck_board_visibility", "visibility IN ('private','team','public-read')")
    with op.batch_alter_table("tasks", naming_convention=NAMING) as batch:
        batch.alter_column("column_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_tasks_column_id_board_columns", "board_columns", ["column_id"], ["id"])
        batch.create_foreign_key("fk_tasks_assignee_id_users", "users", ["assignee_id"], ["id"])
        batch.create_check_constraint("ck_task_position_nonnegative", "position >= 0")
    op.create_index("uq_active_task_position", "tasks", ["board_id", "column_id", "position"], unique=True,
                    sqlite_where=sa.text("is_archived = 0"), postgresql_where=sa.text("is_archived = false"))
    with op.batch_alter_table("labels", naming_convention=NAMING) as batch:
        batch.alter_column("board_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("normalized_name", existing_type=sa.String(), nullable=False)
        batch.create_foreign_key("fk_labels_board_id_boards", "boards", ["board_id"], ["id"])
        batch.create_unique_constraint("uq_label_board_name", ["board_id", "normalized_name"])
    with op.batch_alter_table("attachments", naming_convention=NAMING) as batch:
        batch.create_unique_constraint("uq_attachment_storage_name", ["storage_name"])
    op.create_table(
        "invitations", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(), nullable=False), sa.Column("role", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), unique=True, nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)), sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('admin','member')", name="ck_invitation_role"),
    )
    op.create_table(
        "activity_events", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("board_id", sa.Integer(), sa.ForeignKey("boards.id", ondelete="CASCADE"), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_name", sa.String(), nullable=False), sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False), sa.Column("action", sa.String(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now),
    )
    op.create_index("ix_activity_events_team_id", "activity_events", ["team_id"])
    op.create_index("ix_activity_events_board_id", "activity_events", ["board_id"])
    op.create_index("uq_user_username_ci", "users", [sa.text("lower(username)")], unique=True)
    op.create_index("uq_user_email_ci", "users", [sa.text("lower(email)")], unique=True)


def backfill_ownership_and_columns():
    connection = op.get_bind()
    teams, members, boards, tasks, columns, assignments, board_members = (table(name) for name in
        ("teams", "team_members", "boards", "tasks", "board_columns", "task_members", "board_members"))
    for team in connection.execute(sa.select(teams)).mappings():
        owner = team["created_by_id"]
        connection.execute(sa.update(teams).where(teams.c.id == team["id"]).values(owner_id=owner))
        existing = connection.execute(sa.select(members).where(
            members.c.team_id == team["id"], members.c.user_id == owner)).first()
        if existing:
            connection.execute(sa.update(members).where(members.c.team_id == team["id"],
                members.c.user_id == owner).values(role="owner"))
        else:
            connection.execute(sa.insert(members).values(team_id=team["id"], user_id=owner, role="owner"))
    for board in connection.execute(sa.select(boards).order_by(boards.c.id)).mappings():
        # Upstream is_public never becomes public-write or internet-visible.
        connection.execute(sa.update(boards).where(boards.c.id == board["id"]).values(
            visibility="team" if board["is_public"] else "private"))
        rows = list(connection.execute(sa.select(tasks).where(tasks.c.board_id == board["id"])).mappings())
        statuses = [("todo", "Todo"), ("in_progress", "In Progress"), ("done", "Done")]
        statuses += [(status, status) for status in sorted({row["status"] for row in rows if row["status"]}
                    - {"todo", "in_progress", "done"})]
        for position, (status, name) in enumerate(statuses):
            column_id = connection.execute(sa.insert(columns).values(
                board_id=board["id"], name=name, position=position).returning(columns.c.id)).scalar_one()
            matching = [row for row in rows if (row["status"] or "todo") == status]
            matching.sort(key=lambda row: (row["position"] is None, row["position"] or 0, row["id"]))
            active_index = 0
            for row in matching:
                archived = bool(row["is_archived"])
                assignees = connection.execute(sa.select(assignments.c.user_id).where(
                    assignments.c.task_id == row["id"]).order_by(assignments.c.user_id)).scalars().all()
                permitted_query = sa.select(members.c.user_id).where(
                    members.c.team_id == board["team_id"], members.c.user_id.in_(assignees))
                if not board["is_public"]:
                    explicit_members = sa.select(board_members.c.user_id).where(
                        board_members.c.board_id == board["id"])
                    permitted_query = permitted_query.where(sa.or_(
                        members.c.role.in_(("owner", "admin")),
                        members.c.user_id.in_(explicit_members)))
                permitted = connection.execute(permitted_query.order_by(members.c.user_id)).scalars().all()
                connection.execute(sa.update(tasks).where(tasks.c.id == row["id"]).values(
                    column_id=column_id, position=0 if archived else active_index,
                    is_archived=archived, status=status,
                    assignee_id=permitted[0] if permitted else None,
                    archived_at=datetime.now(timezone.utc) if archived else None,
                ))
                active_index += not archived


def backfill_labels():
    connection = op.get_bind()
    labels, links, tasks, boards = (table(name) for name in ("labels", "task_labels", "tasks", "boards"))
    all_boards = connection.execute(sa.select(boards.c.id).order_by(boards.c.id)).scalars().all()
    used = set()
    for label in list(connection.execute(sa.select(labels).order_by(labels.c.id)).mappings()):
        board_ids = connection.execute(sa.select(tasks.c.board_id).join(
            links, tasks.c.id == links.c.task_id).where(links.c.label_id == label["id"])
            .distinct().order_by(tasks.c.board_id)).scalars().all() or all_boards[:1]
        for index, board_id in enumerate(board_ids):
            original_name = label["name"] or f"Legacy label {label['id']}"
            name = original_name
            normalized = name.strip().casefold()
            attempt = 1
            while (board_id, normalized) in used:
                suffix = str(label["id"]) if attempt == 1 else f"{label['id']}-{attempt}"
                name = f"{original_name} [legacy {suffix}]"
                normalized = name.strip().casefold()
                attempt += 1
            used.add((board_id, normalized))
            if index == 0:
                connection.execute(sa.update(labels).where(labels.c.id == label["id"]).values(
                    board_id=board_id, normalized_name=normalized, name=name))
            else:
                new_id = connection.execute(sa.insert(labels).values(name=name, color=label["color"],
                    board_id=board_id, normalized_name=normalized).returning(labels.c.id)).scalar_one()
                task_ids = sa.select(tasks.c.id).where(tasks.c.board_id == board_id)
                connection.execute(sa.update(links).where(links.c.label_id == label["id"],
                    links.c.task_id.in_(task_ids)).values(label_id=new_id))


def downgrade():
    raise RuntimeError("TeamFlow has data backfills; restore a pre-upgrade backup to downgrade safely")
