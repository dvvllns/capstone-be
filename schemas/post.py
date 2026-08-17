from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, field_validator
from sqlmodel import Field, SQLModel

MAX_IMAGES_PER_POST = 10


class ContentType(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class PostSearchField(StrEnum):
    TITLE = "title"
    CONTENT = "content"
    COMMENT = "comment"
    AUTHOR = "author"


class PostContentBlock(SQLModel):
    """API 요청/응답용 콘텐츠 블록"""

    type: ContentType
    content: str = Field(min_length=1, max_length=10000)
    order: int


def _validate_blocks(blocks: list[PostContentBlock]) -> list[PostContentBlock]:
    """본문 구성을 "텍스트 1개(선택) + 이미지 여러 장" 형태로 제한한다.

    저장 구조는 순서를 가진 블록 배열 그대로지만, 순서를 자유롭게 편집하는
    UI 대신 텍스트를 항상 맨 위에 두는 화면을 쓰기로 해서 그 규칙을 여기서
    강제한다. 나중에 순서 편집을 도입하면 이 검증기만 풀면 된다.
    """
    orders = [b.order for b in blocks]
    if len(set(orders)) != len(orders):
        raise ValueError("블록 순서가 중복되었습니다")

    ordered = sorted(blocks, key=lambda b: b.order)

    texts = [b for b in ordered if b.type == ContentType.TEXT]
    if len(texts) > 1:
        raise ValueError("본문 텍스트는 하나만 사용할 수 있습니다")
    if texts and ordered[0].type != ContentType.TEXT:
        raise ValueError("본문 텍스트는 사진보다 앞에 와야 합니다")

    images = [b for b in ordered if b.type == ContentType.IMAGE]
    if len(images) > MAX_IMAGES_PER_POST:
        raise ValueError(
            f"사진은 최대 {MAX_IMAGES_PER_POST}장까지 첨부할 수 있습니다"
        )

    return blocks


class PostCreate(SQLModel):
    title: str = Field(min_length=1, max_length=40)
    blocks: list[PostContentBlock] = Field(min_length=1)
    is_anonymous: bool = False

    @field_validator("blocks")
    @classmethod
    def blocks_check(
        cls, v: list[PostContentBlock]
    ) -> list[PostContentBlock]:
        return _validate_blocks(v)

    model_config = ConfigDict(str_strip_whitespace=True)


class PostUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=40)
    blocks: list[PostContentBlock] | None = Field(default=None, min_length=1)

    @field_validator("blocks")
    @classmethod
    def blocks_check(
        cls, v: list[PostContentBlock] | None
    ) -> list[PostContentBlock] | None:
        if v is None:
            return v
        return _validate_blocks(v)

    model_config = ConfigDict(str_strip_whitespace=True)


class NoticeUpdate(SQLModel):
    is_notice: bool


class PostResponse(SQLModel):
    id: int
    title: str
    author_nickname: str | None
    views: int
    likes: int
    created_at: datetime
    is_edited: bool
    # 모임 공지로 지정된 글인지. 모임 밖 글은 항상 false다.
    is_notice: bool = False
    blocks: list[PostContentBlock]
    # 익명 글은 author_nickname이 비어 작성자를 알 수 없으므로,
    # 수정/삭제 버튼 노출 여부를 서버가 계산해서 알려준다.
    is_mine: bool = False


class PostLikeResponse(PostResponse):
    liked: bool


class PostListResponse(SQLModel):
    id: int
    title: str
    author_nickname: str | None
    views: int
    likes: int
    created_at: datetime
    # 목록 카드에서 본문 일부와 댓글 수를 보여주기 위한 값.
    # 사진만 있는 글은 preview가 비어 있다.
    preview: str | None = None
    comment_count: int = 0
    # 모임 화면이 공지를 목록에서 빼고 배너로 올리는 데 쓴다.
    is_notice: bool = False
