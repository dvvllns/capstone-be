from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlmodel import Session, col, select

from config import settings
from models.auth import RefreshToken
from security import create_refresh_token, hash_refresh_token


def issue_refresh_token(session: Session, user_id: int) -> str:
    """새 리프레시 토큰을 발급하고 원문을 돌려준다.

    원문은 이때 한 번만 존재한다. 서버에는 해시만 남으므로 잃어버리면
    다시 로그인해야 한다.
    """
    token = create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    session.commit()
    return token


def get_valid_refresh_token(session: Session, token: str) -> RefreshToken | None:
    """살아 있는 토큰이면 그 행을, 아니면 None.

    만료된 행은 그 자리에서 지운다. 어차피 쓸 수 없는 값이라 남겨둘 이유가 없다.
    """
    record = session.exec(
        select(RefreshToken).where(
            col(RefreshToken.token_hash) == hash_refresh_token(token)
        )
    ).first()
    if record is None:
        return None

    if record.expires_at <= datetime.now(timezone.utc):
        session.delete(record)
        session.commit()
        return None
    return record


def revoke_refresh_token(session: Session, token: str) -> None:
    """로그아웃. 이 기기만 끊는다."""
    session.exec(
        delete(RefreshToken).where(
            col(RefreshToken.token_hash) == hash_refresh_token(token)
        )
    )
    session.commit()


def revoke_all_for_user(session: Session, user_id: int) -> None:
    """이 계정의 모든 기기를 끊는다.

    새 로그인, 비밀번호 변경, 탈퇴 때 부른다. 로그인에서도 부르는 이유는
    한 계정을 한 기기에서만 쓰도록 맞추기 위해서다.
    """
    session.exec(delete(RefreshToken).where(col(RefreshToken.user_id) == user_id))
    session.commit()


def purge_expired(session: Session) -> int:
    """만료된 토큰 정리. 주기적으로 부르면 테이블이 무한정 커지지 않는다.

    지울 행을 미리 읽어오지 않는다. 쌓인 토큰이 수만 건이어도 DELETE 한 번으로
    끝나고, 지운 개수는 DB가 알려준다.
    """
    now = datetime.now(timezone.utc)
    result = session.exec(
        delete(RefreshToken).where(col(RefreshToken.expires_at) <= now)
    )
    session.commit()
    return result.rowcount
