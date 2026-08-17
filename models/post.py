from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

from schemas import ContentType

if TYPE_CHECKING:
    from models.comment import Comment
    from models.user import User


class Post(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(min_length=1, max_length=40)
    author_id: int = Field(foreign_key="user.id")
    author_nickname: str | None = None
    group_id: int | None = Field(default=None, foreign_key="groups.id")
    views: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    is_edited: bool = False
    # 모임 공지로 지정된 글. 모임당 하나만 켤 수 있고 모임장만 바꾼다.
    #
    # 모임 화면은 이 글을 목록에서 빼고 맨 위 배너로 따로 보여준다.
    # 모임 밖(수다) 글에는 켤 수 없다.
    is_notice: bool = False

    author: "User" = Relationship(back_populates="posts")
    # 지울 때는 DB에 걸린 ON DELETE CASCADE에 맡긴다.
    #
    # passive_deletes를 주지 않으면 SQLAlchemy가 먼저 자식의 post_id를 NULL로
    # 바꾸려 들고, 그 컬럼은 NOT NULL이라 게시글 삭제가 통째로 실패한다.
    comments: list["Comment"] = Relationship(
        back_populates="post",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    contents: list["PostContent"] = Relationship(
        back_populates="post",
        sa_relationship_kwargs={"passive_deletes": True},
    )


class PostContent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="post.id", ondelete="CASCADE")
    type: ContentType
    content: str = Field(min_length=1, max_length=10000)
    order: int

    post: "Post" = Relationship(back_populates="contents")


class PostLike(SQLModel, table=True):
    post_id: int = Field(foreign_key="post.id", primary_key=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
