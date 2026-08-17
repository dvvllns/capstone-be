from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from config import settings
from crud import auth as auth_crud
from crud import user as user_crud
from database import get_session
from schemas import AccessToken, RefreshRequest, Token
from security import create_access_token

router = APIRouter(prefix="/login", tags=["login"])


def _new_access_token(user_id: int) -> str:
    return create_access_token(
        data={"sub": str(user_id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


@router.post("", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    user = user_crud.authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ID 또는 비밀번호가 올바르지 않습니다",
            headers={"WWW-Authenticate": "Bearer"},
        )

    assert user.id is not None
    # 한 계정은 한 기기에서만 쓴다.
    #
    # 푸시 토큰은 사용자당 하나만 저장되고(FCMToken) 채팅 소켓도 사용자당
    # 하나만 유지된다. 로그인만 여러 기기에 허용하면 앞 기기가 로그인 상태로
    # 남은 채 알림도 실시간 메시지도 못 받는다. 사용자는 이유를 알 수 없다.
    auth_crud.revoke_all_for_user(session, user.id)

    return {
        "access_token": _new_access_token(user.id),
        "refresh_token": auth_crud.issue_refresh_token(session, user.id),
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=AccessToken)
def refresh(
    body: RefreshRequest,
    session: Session = Depends(get_session),
):
    """만료된 액세스 토큰을 새로 받아간다.

    액세스 토큰이 짧아 앱을 오래 안 켜면 매번 만료돼 있다. 이 경로가 없으면
    그때마다 다시 로그인해야 하고, 앱이 꺼진 동안 푸시로 받은 쪽지를 기기에
    저장하는 일도 할 수 없다.
    """
    record = auth_crud.get_valid_refresh_token(session, body.refresh_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="다시 로그인해주세요",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 탈퇴하거나 정지된 계정은 토큰이 남아 있어도 들여보내지 않는다.
    user = user_crud.get_user(session, record.user_id)
    if not user or user.is_deleted:
        auth_crud.revoke_all_for_user(session, record.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="다시 로그인해주세요",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"access_token": _new_access_token(record.user_id), "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    body: RefreshRequest,
    session: Session = Depends(get_session),
):
    """이 기기의 자동 로그인을 끊는다.

    액세스 토큰(JWT)은 서버가 상태를 안 들고 있어 남은 유효 기간 동안은
    계속 통하지만, 리프레시 토큰이 사라지면 갱신이 막혀 곧 끊긴다.
    """
    auth_crud.revoke_refresh_token(session, body.refresh_token)
