from enum import IntEnum

from sqlmodel import SQLModel


class SuspensionDays(IntEnum):
    SEVEN = 7
    THIRTY = 30
    NINETY = 90
    PERMANENT = -1  # 영구 정지


class SuspendUserRequest(SQLModel):
    days: SuspensionDays


class AdminStats(SQLModel):
    """관리자 화면 상단 요약."""

    # 목록에 올라와 있는 신고 대상 수. 처리 상태 컬럼이 없어 지금은
    # 노출 중인 것이 곧 미처리다.
    pending_reports: int
    # 지금 정지 중인 계정 수. 기간이 지난 정지는 세지 않는다.
    suspended_users: int
