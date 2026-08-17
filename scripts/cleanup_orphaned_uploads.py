"""
어디에도 연결되지 않은 채 방치된 업로드 파일을 삭제하는 cron 스크립트.

게시글/프로필/모임 썸네일은 이미지를 먼저 업로드해 URL을 받은 뒤 그 URL을
글/프로필/모임에 붙이는 방식이라, 업로드만 하고 끝까지 연결되지 않은 파일이
생길 수 있다. 업로드 직후(작성 중인 요청)를 잘못 지우지 않도록 일정 유예 시간이
지난 것만 대상으로 한다.

Ubuntu crontab 등록 예시 (매일 새벽 4시 실행):
  0 4 * * * /path/to/venv/bin/python /path/to/scripts/cleanup_orphaned_uploads.py >> /var/log/cleanup_uploads.log 2>&1
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, col, select

from database import engine
from models import Group, PostContent, UploadLog, User
from schemas import ContentType
from utils.image import delete_image

GRACE_PERIOD_HOURS = 1


def run() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=GRACE_PERIOD_HOURS)

    with Session(engine) as session:
        referenced_urls = set(
            session.exec(
                select(PostContent.content).where(
                    PostContent.type == ContentType.IMAGE
                )
            ).all()
        )
        referenced_urls |= set(
            session.exec(
                select(User.profile_pic).where(col(User.profile_pic).is_not(None))
            ).all()
        )
        referenced_urls |= set(
            session.exec(
                select(Group.cover_image).where(col(Group.cover_image).is_not(None))
            ).all()
        )

        candidates = session.exec(
            select(UploadLog).where(col(UploadLog.uploaded_at) < cutoff)
        ).all()
        orphaned = [log for log in candidates if log.url not in referenced_urls]

        if not orphaned:
            print(f"[{datetime.now()}] 정리할 고아 파일 없음")
            return

        for log in orphaned:
            delete_image(log.url)
            session.delete(log)
        session.commit()
        print(f"[{datetime.now()}] 고아 파일 {len(orphaned)}개 정리 완료")


if __name__ == "__main__":
    run()
