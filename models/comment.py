from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import ConfigDict
from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from models.post import Post
    from models.user import User


class Comment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    content: str = Field(min_length=1, max_length=1000)
    author_id: int = Field(foreign_key="user.id")
    author_nickname: str | None = None
    post_id: int = Field(foreign_key="post.id", ondelete="CASCADE")
    # 대댓글 구현 위해 만듦
    parent_id: int | None = Field(default=None, foreign_key="comment.id")
    likes: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    is_edited: bool = False

    parent: Optional["Comment"] = Relationship(
        back_populates="children", sa_relationship_kwargs={"remote_side": "Comment.id"}
    )
    children: list["Comment"] = Relationship(back_populates="parent")
    author: "User" = Relationship(back_populates="comments")
    post: "Post" = Relationship(back_populates="comments")

    model_config = ConfigDict(str_strip_whitespace=True)


class CommentLike(SQLModel, table=True):
    comment_id: int = Field(
        foreign_key="comment.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
