"""Validated account/team/board inputs. Task inputs live in tasks/schemas.py."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

class UserCreate(Input):
    email: str = Field(min_length=3, max_length=254)
    username: str = Field(min_length=2, max_length=48, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str | None = Field(default=None, max_length=100)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value

class TeamCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

class TeamUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

class BoardCreate(TeamCreate):
    visibility: Literal["private", "team", "public-read"] = "team"
    team_id: int | None = None

class MemberUpdate(Input):
    role: Literal["admin", "member"]

class BoardMemberCreate(MemberUpdate):
    user_id: int
    role: Literal["admin", "member"] = "member"

class OwnershipTransfer(Input):
    user_id: int

class InviteCreate(Input):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["admin", "member"] = "member"
    _email = field_validator("email")(UserCreate.email_address.__func__)

class InviteAccept(Input):
    token: str = Field(min_length=32, max_length=200)