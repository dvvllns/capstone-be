from pydantic import BaseModel


class Token(BaseModel):
    """로그인 응답.

    access_token은 30분이면 만료된다. refresh_token은 그때 새 access_token을
    받아오기 위한 것으로, 기기에 오래 보관한다.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    """갱신 응답. 리프레시 토큰은 그대로 쓰므로 다시 내려보내지 않는다."""

    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    """토큰에서 추출한 데이터"""

    user_id: int
