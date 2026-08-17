import re
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import ConfigDict, EmailStr, field_validator
from sqlalchemy import Date, DateTime, Index, text
from sqlmodel import AutoString, Field, Relationship, SQLModel

from utils.profanity import contains_profanity

PHONE_NUMBER_PATTERN = re.compile(r"010[0-9]{8}")


def validate_phone_number(v: str) -> str:
    """한국 휴대폰 번호(010으로 시작하는 11자리 숫자) 형식 검증"""
    if not PHONE_NUMBER_PATTERN.fullmatch(v):
        raise ValueError("휴대폰 번호는 010으로 시작하는 11자리 숫자여야 합니다")
    return v


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


# 탈퇴 계정에 덮어쓰는 값. 사칭을 막기 위해 가입/변경 시 사용할 수 없다.
DELETED_NICKNAME = "탈퇴한 사용자"
# 강퇴된 멤버가 그 모임에 남긴 글의 작성자 표시
KICKED_NICKNAME = "(알 수 없음)"
RESERVED_NICKNAMES = frozenset({DELETED_NICKNAME, KICKED_NICKNAME})


def validate_nickname(v: str) -> str:
    if v in RESERVED_NICKNAMES:
        raise ValueError("사용할 수 없는 닉네임입니다")
    # 닉네임은 글과 댓글마다 계속 보이는 이름이라 욕설을 막는다.
    # 가입과 변경 양쪽이 이 함수를 지나므로 여기 한 곳에서 검사한다.
    if contains_profanity(v):
        raise ValueError("닉네임에 사용할 수 없는 표현이 있습니다")
    return v


if TYPE_CHECKING:
    from models.comment import Comment
    from models.post import Post


class UserBase(SQLModel):
    # 유일성은 User.__table_args__의 부분 유니크 인덱스가 담당한다.
    # 탈퇴한 계정이 값을 놓아주게 하려면 unique=True(전체 유니크)를 쓸 수 없다.
    login_id: str = Field(min_length=4, max_length=20)
    email: EmailStr | None = Field(default=None)
    phone_number: str = Field(min_length=11, max_length=11)
    nickname: str = Field(min_length=1, max_length=15)
    date_of_birth: date = Field(
        ge=date(1900, 1, 1), le=date(2005, 12, 31), sa_type=Date()
    )
    gender: Gender = Field(sa_type=AutoString())
    profile_pic: str | None = None

    @field_validator("login_id")
    @classmethod
    # 로그인 ID는 영문 소문자, 숫자로 구성
    def login_id_check(cls, v: str) -> str:
        if not (v.isascii() and v.isalnum()):
            raise ValueError("ID는 영문자와 숫자만 허용됩니다")
        return v.lower()

    @field_validator("phone_number")
    @classmethod
    def phone_number_check(cls, v: str) -> str:
        return validate_phone_number(v)

    @field_validator("nickname")
    @classmethod
    def nickname_check(cls, v: str) -> str:
        return validate_nickname(v)

    model_config = ConfigDict(str_strip_whitespace=True)


def _active_unique(name: str, column: str) -> Index:
    """탈퇴하지 않은 행들 사이에서만 유일하도록 하는 부분 유니크 인덱스.

    전체 유니크로 두면 탈퇴 계정이 아이디/번호/닉네임을 계속 붙들고 있어
    같은 번호로 다시 가입할 수 없다. PostgreSQL 전용 기능이다.
    """
    return Index(name, column, unique=True, postgresql_where=text("is_deleted = false"))


class User(UserBase, table=True):
    __table_args__ = (
        _active_unique("uq_user_login_id_active", "login_id"),
        _active_unique("uq_user_phone_number_active", "phone_number"),
        _active_unique("uq_user_nickname_active", "nickname"),
        _active_unique("uq_user_email_active", "email"),
        # 탈퇴 여부와 무관한 조회용. 부분 인덱스는 조건이 맞을 때만 쓰인다.
        Index("ix_user_login_id", "login_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    is_admin: bool = False
    is_deleted: bool = False
    default_anonymous: bool = False
    notify_message: bool = True
    suspended_until: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )

    posts: list["Post"] = Relationship(back_populates="author")
    comments: list["Comment"] = Relationship(back_populates="author")


class UserBlock(SQLModel, table=True):
    blocker_id: int = Field(foreign_key="user.id", primary_key=True)
    blocked_id: int = Field(foreign_key="user.id", primary_key=True)
    # 차단 이전에 주고받은 대화는 그대로 보여야 하므로 시점을 남긴다.
    # 이 시각 이후에 상대가 보낸 쪽지만 가린다.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
