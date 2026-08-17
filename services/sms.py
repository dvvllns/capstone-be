from fastapi import HTTPException, status
from solapi import SolapiMessageService
from solapi.model.request.message import Message

from config import settings

_service: SolapiMessageService | None = None


def _get_service() -> SolapiMessageService:
    global _service
    if _service is None:
        _service = SolapiMessageService(
            api_key=settings.SOLAPI_API_KEY, api_secret=settings.SOLAPI_API_SECRET
        )
    return _service


def send_sms(to: str, text: str) -> None:
    """SOLAPI를 통해 SMS 발송"""
    message = Message(from_=settings.SOLAPI_SENDER_PHONE, to=to, text=text)
    try:
        _get_service().send(message)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="SMS 발송에 실패했습니다"
        )
