from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey, Table,
                        Boolean, JSON, UniqueConstraint, CheckConstraint, Index, text)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .database import Base

# Association tables for many-to-many relationships
task_labels = Table(
    'task_labels',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id')),
    Column('label_id', Integer, ForeignKey('labels.id'))
)

task_members = Table(
    'task_members',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id')),
    Column('user_id', Integer, ForeignKey('users.id'))
)

class TeamMember(Base):
    __tablename__ = "team_members"

    team_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role = Column(String, default='member')  # Can be 'admin' or 'member'
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    team = relationship("Team", back_populates="team_memberships")
    user = relationship("User", back_populates="team_memberships")

class BoardMember(Base):
    __tablename__ = "board_members"

    board_id = Column(Integer, ForeignKey("boards.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role = Column(String, default='member')  # Can be 'admin' or 'member'
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    board = relationship("Board", back_populates="board_memberships")
    user = relationship("User", back_populates="board_memberships")

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    membership_revision = Column(Integer, nullable=False, default=0, server_default="0")
    
    # Relationships
    team_memberships = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    members = relationship(
        "User",
        secondary="team_members",
        back_populates="member_of_teams",
        viewonly=True,  # Make this view-only since we manage through team_memberships
        overlaps="team_memberships"
    )
    boards = relationship("Board", back_populates="team", cascade="all, delete-orphan")
    created_by = relationship("User", foreign_keys=[created_by_id])

class Board(Base):
    __tablename__ = "boards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"))
    team_id = Column(Integer, ForeignKey("teams.id"))
    is_public = Column(Boolean, default=False)  # If true, visible to all team members
    visibility = Column(String, nullable=False, default="team", server_default="team")
    revision = Column(Integer, nullable=False, default=0, server_default="0")
    __table_args__ = (CheckConstraint("visibility IN ('private','team','public-read')", name="ck_board_visibility"),)
    
    # Relationships
    board_memberships = relationship("BoardMember", back_populates="board", cascade="all, delete-orphan")
    team = relationship("Team", back_populates="boards")
    members = relationship(
        "User",
        secondary="board_members",
        back_populates="member_of_boards",
        viewonly=True,  # Make this view-only since we manage through board_memberships
        overlaps="board_memberships"
    )
    tasks = relationship("Task", back_populates="board", cascade="all, delete-orphan")
    columns = relationship("BoardColumn", cascade="all, delete-orphan", order_by="BoardColumn.position")
    labels = relationship("Label", cascade="all, delete-orphan")
    created_by = relationship("User", foreign_keys=[created_by_id])

class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class TaskPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("uq_user_username_ci", func.lower(username), unique=True),
        Index("uq_user_email_ci", func.lower(email), unique=True),
    )
    
    # Relationships
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    assigned_tasks = relationship("Task", secondary=task_members, back_populates="assigned_to")
    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")
    board_memberships = relationship("BoardMember", back_populates="user", cascade="all, delete-orphan")
    member_of_teams = relationship(
        "Team",
        secondary="team_members",
        back_populates="members",
        viewonly=True,  # Make this view-only since we manage through team_memberships
        overlaps="team_memberships"
    )
    member_of_boards = relationship(
        "Board",
        secondary="board_members",
        back_populates="members",
        viewonly=True,  # Make this view-only since we manage through board_memberships
        overlaps="board_memberships"
    )

class Label(Base):
    __tablename__ = "labels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    color = Column(String)
    board_id = Column(Integer, ForeignKey("boards.id"), nullable=False)
    normalized_name = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("board_id", "normalized_name", name="uq_label_board_name"),)
    
    # Relationships
    tasks = relationship("Task", secondary=task_labels, back_populates="labels")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    status = Column(String, default=TaskStatus.TODO)
    priority = Column(String, default=TaskPriority.LOW)
    position = Column(Integer, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    creator_id = Column(Integer, ForeignKey("users.id"))
    board_id = Column(Integer, ForeignKey("boards.id"))
    is_archived = Column(Boolean, default=False)
    checklist = Column(JSON, default=list)
    column_id = Column(Integer, ForeignKey("board_columns.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_task_position_nonnegative"),
        Index("uq_active_task_position", "board_id", "column_id", "position", unique=True,
              sqlite_where=text("is_archived = 0"), postgresql_where=text("is_archived = false")),
    )
    
    # Relationships
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    assignee = relationship("User", foreign_keys=[assignee_id])
    board = relationship("Board", back_populates="tasks")
    assigned_to = relationship("User", secondary=task_members, back_populates="assigned_tasks")
    labels = relationship("Label", secondary=task_labels, back_populates="tasks")
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="task", cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    task_id = Column(Integer, ForeignKey("tasks.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    task = relationship("Task", back_populates="comments")
    user = relationship("User")

    @property
    def user_name(self) -> str:
        return self.user.username if self.user else "Unknown User"

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    file_path = Column(String)
    url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    task_id = Column(Integer, ForeignKey("tasks.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    storage_name = Column(String, unique=True, nullable=True)
    original_name = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    
    # Relationships
    task = relationship("Task", back_populates="attachments")
    user = relationship("User")


class BoardColumn(Base):
    __tablename__ = "board_columns"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("boards.id"), nullable=False)
    name = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    wip_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("board_id", "position", name="uq_column_position"),
        CheckConstraint("position >= 0", name="ck_column_position_nonnegative"),
        CheckConstraint("wip_limit IS NULL OR wip_limit > 0", name="ck_column_wip"),
    )


class Invitation(Base):
    __tablename__ = "invitations"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("role IN ('admin','member')", name="ck_invitation_role"),)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
