import firebase_admin
from firebase_admin import credentials, messaging

from config import BASE_DIR, settings

_app: firebase_admin.App | None = None

FCM_BODY_MAX_LEN = 100


def _get_app() -> firebase_admin.App:
    global _app
    if _app is None:
        # 설정값이 상대 경로여도 실행 위치에 휘둘리지 않게 한다.
        cred = credentials.Certificate(str(BASE_DIR / settings.FIREBASE_CREDENTIALS_PATH))
        _app = firebase_admin.initialize_app(cred)
    return _app


def send_chat_notification(
    *,
    fcm_token: str,
    sender_nickname: str,
    content: str,
    room_id: int,
    show_content: bool,
) -> None:
    """채팅 메시지 FCM 푸시 알림 전송.

    show_content=False이면 본문에 내용을 포함하지 않음 (수신자의 notify_message 설정).

    푸시 실패가 채팅 흐름을 막으면 안 되므로 초기화 실패까지 포함해 삼킨다.
    인증서가 없거나 잘못된 환경에서도 메시지 전송 자체는 계속 동작해야 한다.
    """
    if show_content:
        body_text = content if len(content) <= FCM_BODY_MAX_LEN else content[:FCM_BODY_MAX_LEN] + "..."
    else:
        body_text = "새 메시지가 있습니다"

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=sender_nickname,
                body=body_text,
            ),
            data={"room_id": str(room_id)},
            # 기기가 절전 상태여도 바로 깨우도록 한다. 받은 쪽은 이 신호로
            # 밀린 메시지를 내려받아 기기에 저장하므로 지연되면 곤란하다.
            android=messaging.AndroidConfig(priority="high"),
            token=fcm_token,
        )
        messaging.send(message, app=_get_app())
    except Exception:
        pass
