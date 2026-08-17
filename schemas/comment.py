from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class CommentCreate(SQLModel):
    content: str = Field(min_length=1, max_length=1000)
    is_anonymous: bool = False

    model_config = ConfigDict(
        str_strip_whitespace=True  # 문자열 앞뒤 whitespace 자동 제거
    )


class CommentUpdate(CommentCreate):
    pass


class CommentResponse(SQLModel):
    id: int
    content: str
    author_nickname: str | None
    post_id: int
    parent_id: int | None
    likes: int
    created_at: datetime
    is_edited: bool
    is_blocked: bool = False
    # 익명 댓글도 본인 것인지 판단할 수 있게 서버가 계산해서 내려준다.
    is_mine: bool = False


class CommentLikeResponse(CommentResponse):
    liked: bool
