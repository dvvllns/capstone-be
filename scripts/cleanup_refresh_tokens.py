"""
만료된 리프레시 토큰을 DB에서 삭제하는 cron 스크립트.

토큰은 만료돼도 행이 남는다. 로그인할 때마다 한 줄씩 쌓이므로 치우지 않으면
refresh_token 테이블만 계속 커진다. 만료된 토큰은 이미 인증에 쓸 수 없으니
지워도 잃는 것이 없다.

Ubuntu crontab 등록 예시 (매일 새벽 5시 실행):
  0 5 * * * /path/to/venv/bin/python /path/to/scripts/cleanup_refresh_tokens.py >> /var/log/cleanup_tokens.log 2>&1
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session

from crud import auth as auth_crud
from database import engine


def run() -> None:
    # 지우는 조건(만료 시각 비교)은 crud에 이미 있다. 여기서 다시 쓰면
    # 나중에 한쪽만 고쳐져 어긋난다.
    with Session(engine) as session:
        count = auth_crud.purge_expired(session)

    if count == 0:
        print(f"[{datetime.now()}] 삭제할 토큰 없음")
        return
    print(f"[{datetime.now()}] 만료 토큰 {count}개 삭제 완료")


if __name__ == "__main__":
    run()
