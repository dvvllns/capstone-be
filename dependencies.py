from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlmodel import Session

from config import settings
from crud import user as user_crud
from database import get_session
from models import User
from schemas import TokenData

# 토큰 URL 지정 (로그인 엔드포인트)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)
) -> User:
    """토큰 검증, 현재 사용자 반환"""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 토큰 디코딩
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str | None = payload.get("sub")

        if not user_id:
            raise credentials_exception
        token_data = TokenData(user_id=int(user_id))

    except PyJWTError:
        raise credentials_exception

    # 사용자 조회
    user = user_crud.get_user(session, token_data.user_id)

    if not user:
        raise credentials_exception

    # 탈퇴한 계정의 토큰은 만료 전이라도 더 이상 쓸 수 없어야 한다.
    if user.is_deleted:
        raise credentials_exception

    if user.suspended_until and user.suspended_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"계정이 정지되었습니다. 정지 해제일: {user.suspended_until.strftime('%Y-%m-%d')}",
        )
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """관리자 권한 확인"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다",
        )
    return current_user


class Pagination:
    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="페이지 번호"),
        size: int = Query(default=10, ge=1, le=100, description="페이지 크기"),
    ):
        self.page = page
        self.size = size
        self.skip = (page - 1) * size
