from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskCreate(RequestModel):
    title: str = Field(min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=20000)
    column_id: int
    priority: Literal["low", "medium", "high"] = "low"
    due_date: datetime | None = None
    assignee_id: int | None = None

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip():
            raise ValueError("Title must contain text")
        return value.strip()


class TaskUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=20000)
    priority: Literal["low", "medium", "high"] | None = None
    due_date: datetime | None = None
    assignee_id: int | None = None
    is_archived: bool | None = None
    expected_revision: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Title must contain text")
        return value.strip() if value else value


class TaskMove(RequestModel):
    target_column_id: int
    target_index: int = Field(ge=0)
    expected_revision: int = Field(ge=0)
    expected_version: int | None = Field(default=None, ge=1)


class LabelCreate(RequestModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Name must contain text")
        return value.strip()


class CommentCreate(RequestModel):
    content: str = Field(min_length=1, max_length=10000)
    task_id: int | None = None

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value):
        if not value.strip():
            raise ValueError("Content must contain text")
        return value.strip()


class ChecklistCreate(RequestModel):
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value):
        if not value.strip():
            raise ValueError("Content must contain text")
        return value.strip()


class ColumnCreate(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    wip_limit: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("Name must contain text")
        return value.strip()


class ColumnUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    wip_limit: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Name must contain text")
        return value.strip() if value else value


class ColumnReorder(RequestModel):
    column_ids: list[int] = Field(min_length=1)
    expected_revision: int | None = Field(default=None, ge=0)


class BoardUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=20000)
    visibility: Literal["private", "team", "public-read"] | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Name must contain text")
        return value.strip() if value else value
