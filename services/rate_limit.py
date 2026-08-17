import time

from fastapi import HTTPException, status

from redis_client import redis_client


def check_rate_limit(
    key: str,
    *,
    cooldown_seconds: int,
    max_count: int,
    window_seconds: int,
    cooldown_message: str,
    limit_message: str,
) -> None:
    """쿨다운 + 윈도우 카운트 기반 rate limit 검사.

    key 하나에 마지막 요청 시각(last_at)과 윈도우 내 횟수(count)를 같이 저장하고,
    윈도우 TTL은 count가 처음 생성될 때만 걸어 "첫 요청 시점부터 window_seconds 동안"
    롤링되는 윈도우로 동작하게 한다. cooldown_message에 "{wait}"를 넣으면 남은 대기
    초가 채워진다.
    """
    now = time.time()

    last_at = redis_client.hget(key, "last_at")
    if last_at is not None and now - float(last_at) < cooldown_seconds:
        wait = int(cooldown_seconds - (now - float(last_at)))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=cooldown_message.format(wait=wait),
        )

    count = redis_client.hincrby(key, "count", 1)
    if count == 1:
        redis_client.expire(key, window_seconds)
    if count > max_count:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=limit_message,
        )

    redis_client.hset(key, "last_at", now)
