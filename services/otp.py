import hashlib
import secrets
from enum import StrEnum

from fastapi import HTTPException, status

from redis_client import redis_client
from services.rate_limit import check_rate_limit
from services.sms import send_sms

OTP_LENGTH = 6
OTP_TTL_SECONDS = 180  # 3분
MAX_VERIFY_ATTEMPTS = 5

# 인증 성공 후 실제 가입/번호변경까지 허용하는 시간
VERIFIED_TTL_SECONDS = 15 * 60  # 15분

RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_WINDOW = 10
SEND_WINDOW_SECONDS = 24 * 60 * 60  # 24시간


class OTPPurpose(StrEnum):
    SIGNUP = "signup"
    CHANGE_PHONE = "change_phone"


def _otp_key(purpose: OTPPurpose, phone_number: str) -> str:
    return f"otp:{purpose}:{phone_number}"


def _send_limit_key(purpose: OTPPurpose, phone_number: str) -> str:
    return f"otp_send:{purpose}:{phone_number}"


def _verified_key(purpose: OTPPurpose, phone_number: str) -> str:
    return f"otp_verified:{purpose}:{phone_number}"


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _check_send_limit(purpose: OTPPurpose, phone_number: str) -> None:
    """재전송 쿨다운(60초)과 24시간 기준 발송 횟수(10회) 제한 검사"""
    check_rate_limit(
        _send_limit_key(purpose, phone_number),
        cooldown_seconds=RESEND_COOLDOWN_SECONDS,
        max_count=MAX_SENDS_PER_WINDOW,
        window_seconds=SEND_WINDOW_SECONDS,
        cooldown_message="{wait}초 후 다시 시도해주세요",
        limit_message="인증번호 발송 횟수를 초과했습니다. 24시간 후 다시 시도해주세요",
    )


def send_otp(phone_number: str, purpose: OTPPurpose) -> None:
    """OTP를 생성해 Redis Hash(코드+시도횟수)에 저장하고 SOLAPI로 발송.

    코드와 시도횟수를 하나의 key에 같이 두어 TTL을 하나로 공유한다.
    """
    _check_send_limit(purpose, phone_number)

    code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
    key = _otp_key(purpose, phone_number)
    redis_client.hset(key, mapping={"code": _hash_otp(code), "attempts": 0})
    redis_client.expire(key, OTP_TTL_SECONDS)
    send_sms(phone_number, f"[인증번호] {code} (3분 이내 입력해주세요)")


def verify_otp(phone_number: str, purpose: OTPPurpose, code: str) -> None:
    """OTP 검증. 실패 시 예외 발생, 성공 시 재사용 방지를 위해 즉시 삭제.

    성공하면 인증 완료 표식을 남겨, 이후 실제 작업(가입/번호변경) 요청이
    VERIFIED_TTL_SECONDS 안에 consume_verification으로 이를 확인할 수 있게 한다.
    """
    key = _otp_key(purpose, phone_number)
    if not redis_client.exists(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증번호가 올바르지 않거나 만료되었습니다",
        )

    attempts = redis_client.hincrby(key, "attempts", 1)
    if attempts > MAX_VERIFY_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요",
        )

    stored = redis_client.hget(key, "code")
    if stored is None or stored != _hash_otp(code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증번호가 올바르지 않거나 만료되었습니다",
        )
    redis_client.delete(key)
    redis_client.set(
        _verified_key(purpose, phone_number), "1", ex=VERIFIED_TTL_SECONDS
    )


def consume_verification(phone_number: str, purpose: OTPPurpose) -> None:
    """인증 완료 표식을 소비한다. 없으면(미인증·만료) 예외 발생.

    표식 확인과 삭제를 delete 한 번으로 처리해 재사용을 막는다.
    """
    if not redis_client.delete(_verified_key(purpose, phone_number)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="휴대폰 인증이 필요합니다. 인증번호를 다시 요청해주세요",
        )
