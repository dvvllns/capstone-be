from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from schemas.group import ApplicationStatus


class Group(SQLModel, table=True):
    __tablename__ = "groups"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=500)
    cover_image: str | None = None
    leader_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class GroupMember(SQLModel, table=True):
    group_id: int = Field(foreign_key="groups.id", primary_key=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class GroupApplication(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id")
    status: ApplicationStatus = ApplicationStatus.PENDING
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
