import re
from enum import StrEnum
from datetime import date, datetime

from pydantic import ConfigDict, EmailStr, field_validator
from sqlmodel import Field, SQLModel

from models.user import (
    DELETED_NICKNAME,
    Gender,
    UserBase,
    validate_nickname,
    validate_phone_number,
)

_ALLOWED_PASSWORD_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;:,.<>?/~"
)
_OTP_PATTERN = re.compile(r"[0-9]{6}")


def _validate_password(v: str) -> str:
    if not all(c in _ALLOWED_PASSWORD_CHARS for c in v):
        raise ValueError("비밀번호에 허용되지 않은 문자를 사용했습니다")
    if not any(c.isalpha() for c in v):
        raise ValueError("비밀번호는 영문자를 포함해야 합니다")
    if not any(c.isdigit() for c in v):
        raise ValueError("비밀번호는 숫자를 포함해야 합니다")
    return v


def _validate_otp(v: str) -> str:
    if not _OTP_PATTERN.fullmatch(v):
        raise ValueError("인증번호는 숫자 6자리여야 합니다")
    return v


class NicknameRejection(StrEnum):
    """닉네임을 쓸 수 없는 이유. 화면이 그에 맞는 안내를 하도록 구분해 준다."""

    TAKEN = "taken"
    RESERVED = "reserved"
    PROFANITY = "profanity"


class UserCreate(UserBase):
    """회원가입"""

    password: str = Field(min_length=8, max_length=32)

    @field_validator("password")
    @classmethod
    def password_check(cls, v: str) -> str:
        return _validate_password(v)


class UserUpdate(SQLModel):
    """사용자 정보 수정"""

    password: str | None = Field(default=None, min_length=8, max_length=32)
    email: EmailStr | None = Field(default=None)
    nickname: str | None = Field(default=None, min_length=1, max_length=15)

    @field_validator("nickname")
    @classmethod
    def nickname_check(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_nickname(v)
    profile_pic: str | None = None
    default_anonymous: bool | None = None
    notify_message: bool | None = None

    @field_validator("password")
    @classmethod
    def password_check(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_password(v)

    model_config = ConfigDict(str_strip_whitespace=True)


class PhoneOTPRequest(SQLModel):
    """휴대폰 인증번호 발송 요청 (회원가입/번호 변경 공용)"""

    phone_number: str = Field(min_length=11, max_length=11)

    @field_validator("phone_number")
    @classmethod
    def phone_number_check(cls, v: str) -> str:
        return validate_phone_number(v)

    model_config = ConfigDict(str_strip_whitespace=True)


class PhoneOTPVerifyRequest(PhoneOTPRequest):
    """휴대폰 인증번호 검증 요청 (회원가입/번호 변경 공용)"""

    otp: str = Field(min_length=6, max_length=6, description="휴대폰 인증번호")

    @field_validator("otp")
    @classmethod
    def otp_check(cls, v: str) -> str:
        return _validate_otp(v)


class PhoneNumberUpdate(PhoneOTPRequest):
    """휴대폰 번호 변경 (인증은 검증 엔드포인트에서 선행)"""


class PasswordVerifyRequest(SQLModel):
    """현재 비밀번호 확인 (닉네임/비밀번호 변경 등 민감한 작업 전에 사용)"""

    password: str = Field(min_length=1, max_length=32)


class BlockRequest(SQLModel):
    """닉네임으로 사용자 차단/해제"""

    nickname: str = Field(min_length=1, max_length=15)

    model_config = ConfigDict(str_strip_whitespace=True)


class BlockedUserResponse(SQLModel):
    """차단 목록 항목"""

    id: int
    nickname: str


class UserResponse(SQLModel):
    """사용자 응답 (비밀번호 제외)"""

    id: int
    login_id: str
    is_admin: bool = False
    email: EmailStr | None
    phone_number: str
    nickname: str
    date_of_birth: date
    gender: Gender
    created_at: datetime
    profile_pic: str | None
    default_anonymous: bool
    notify_message: bool
