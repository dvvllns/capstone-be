"""
7일 이상 된 채팅 메시지를 DB에서 삭제하는 cron 스크립트.

Ubuntu crontab 등록 예시 (매일 새벽 3시 실행):
  0 3 * * * /path/to/venv/bin/python /path/to/scripts/cleanup_messages.py >> /var/log/cleanup_messages.log 2>&1

MessageReadReceipt는 chat_message.id에 ondelete="CASCADE" FK가 걸려 있으므로
메시지 삭제 시 PostgreSQL이 자동으로 함께 삭제합니다.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete
from sqlmodel import Session, col

from database import engine
from models.chat import ChatMessage

RETENTION_DAYS = 7


def run() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

    with Session(engine) as session:
        # 몇 건인지 세려고 메시지를 먼저 읽어오지 않는다. 메시지는 이 서비스에서
        # 가장 많이 쌓이는 자료라, 세기만 하려고 전부 메모리에 올리면 정리하다
        # 서버가 먼저 넘어간다. 지운 개수는 DELETE가 알려준다.
        result = session.exec(
            delete(ChatMessage).where(col(ChatMessage.created_at) < cutoff)
        )
        session.commit()
        count = result.rowcount

    if count == 0:
        print(f"[{datetime.now()}] 삭제할 메시지 없음")
        return
    print(f"[{datetime.now()}] 메시지 {count}개 삭제 완료 ({RETENTION_DAYS}일 이상)")


if __name__ == "__main__":
    run()
