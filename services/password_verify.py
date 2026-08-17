from fastapi import HTTPException, status

from redis_client import redis_client
from security import verify_password

MAX_VERIFY_ATTEMPTS = 5
LOCK_TTL_SECONDS = 10 * 60  # 시도 횟수를 세는 창(10분)


def _attempt_key(user_id: int) -> str:
    return f"pw_verify:{user_id}"


def verify_current_password(user_id: int, hashed_password: str, password: str) -> None:
    """현재 비밀번호 확인.

    비밀번호를 바꾸거나 계정을 지우기 전에 본인 확인용으로 쓴다. 무제한으로
    시도하면 기기를 잠깐 손에 넣은 사람이 비밀번호를 알아낼 수 있으므로
    10분 안에 MAX_VERIFY_ATTEMPTS번 실패하면 더 받지 않는다.
    """
    key = _attempt_key(user_id)

    attempts = int(redis_client.get(key) or 0)
    if attempts >= MAX_VERIFY_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="비밀번호 확인 시도 횟수를 초과했습니다. 잠시 후 다시 시도해주세요",
        )

    if not verify_password(hashed_password, password):
        # 첫 실패에만 TTL을 걸어 "첫 실패 시점부터 10분" 창으로 동작하게 한다.
        if redis_client.incr(key) == 1:
            redis_client.expire(key, LOCK_TTL_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호가 올바르지 않습니다",
        )

    # 성공하면 실패 기록을 지운다.
    redis_client.delete(key)
