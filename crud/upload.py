from datetime import datetime, timedelta, timezone

from sqlmodel import Session, func, select

from models import UploadLog

# window = 시간 구간
WINDOW_MINUTES = 10
MAX_BYTES_PER_WINDOW = 100 * 1024 * 1024  # 100MB


def get_user_uploaded_bytes(session: Session, user_id: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)
    statement = select(func.sum(UploadLog.file_size)).where(
        UploadLog.user_id == user_id,
        UploadLog.uploaded_at >= cutoff,
    )
    return session.exec(statement).first() or 0


def check_upload_limit(session: Session, user_id: int, file_size: int) -> bool:
    used = get_user_uploaded_bytes(session, user_id)
    return used + file_size <= MAX_BYTES_PER_WINDOW


def log_upload(session: Session, user_id: int, file_size: int, url: str) -> None:
    session.add(UploadLog(user_id=user_id, file_size=file_size, url=url))
    session.commit()


def delete_log_by_url(session: Session, url: str) -> None:
    log = session.exec(select(UploadLog).where(UploadLog.url == url)).first()
    if log:
        session.delete(log)
        session.commit()
