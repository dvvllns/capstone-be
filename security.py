import hashlib
import secrets
from datetime import datetime, timezone, timedelta
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from config import settings

ph = PasswordHasher()


def create_refresh_token() -> str:
    """추측할 수 없는 무작위 문자열. 리프레시 토큰의 원문이다."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """DB에 저장할 형태.

    비밀번호와 달리 사람이 만든 값이 아니라 무작위 32바이트라, 사전 공격이
    통하지 않는다. 그래서 argon2 같은 느린 해시 대신 SHA-256을 쓴다.
    매 요청마다 조회해야 하므로 빠른 편이 낫다.
    """
    return hashlib.sha256(token.encode()).hexdigest()

def verify_password(hashed_password: str, plain_password: str) -> bool:
    """비밀번호 검증"""
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False

def get_password_hash(password: str) -> str:
    """hashed_password 구하기"""
    return ph.hash(password)

#data에 담긴 정보가 JWT의 페이로드
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """JWT 토큰 생성"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt
