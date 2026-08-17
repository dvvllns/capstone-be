from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class RefreshToken(SQLModel, table=True):
    """자동 로그인을 위한 장기 토큰.

    액세스 토큰은 30분이면 만료된다. 그때마다 다시 로그인하게 할 수는 없으므로
    수명이 긴 토큰을 따로 두고, 이것으로 새 액세스 토큰을 받아간다.

    액세스 토큰(JWT)은 서버가 상태를 들고 있지 않아 개별 무효화가 안 되지만,
    이 토큰은 여기 행으로 존재하므로 지우면 즉시 끊긴다. 기기를 잃어버렸을 때
    그 기기만 끊을 수 있는 이유가 이것이다.

    원문 대신 해시를 저장한다. DB가 통째로 새어 나가도 그것만으로는 로그인할
    수 없다. 토큰은 무작위 32바이트라 추측이 불가능하므로, 비밀번호와 달리
    느린 해시가 필요 없고 SHA-256으로 충분하다.
    """

    __tablename__ = "refresh_token"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(unique=True, index=True)
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
