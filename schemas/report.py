from datetime import datetime
from enum import StrEnum

from sqlmodel import SQLModel


class ReportReason(StrEnum):
    SPAM = "spam"
    HATE = "hate"
    SEXUAL = "sexual"
    SELF_HARM = "self_harm"
    PRIVACY = "privacy"
    OTHER = "other"


class TargetType(StrEnum):
    POST = "post"
    COMMENT = "comment"


class ReportStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"


class ReportAction(StrEnum):
    """신고를 어떻게 처리했는지.

    SUSPENDED는 관리자만, KICKED는 모임장만 쓴다. 모임장에게 계정 정지까지
    맡기면 모임 하나 때문에 앱 전체를 못 쓰게 만들 수 있다.
    """

    DELETED = "deleted"
    SUSPENDED = "suspended"
    KICKED = "kicked"
    # 신고를 봤지만 문제가 없다고 판단한 경우. 목록에서 내리되 기록은 남긴다.
    DISMISSED = "dismissed"


class ReportCreate(SQLModel):
    reason: ReportReason


class ReportListItem(SQLModel):
    id: int
    reporter_id: int
    target_type: TargetType
    target_id: int
    reason: ReportReason
    created_at: datetime


class ReportReasonCount(SQLModel):
    reason: ReportReason
    count: int


class ReportedTarget(SQLModel):
    """여러 번 신고된 글이나 댓글 하나.

    신고를 낱개로 내려주면 같은 글이 신고당한 횟수만큼 목록에 반복된다.
    관리자는 "이 글이 몇 명에게 신고됐는지"를 보고 판단하므로 대상 단위로 묶는다.
    """

    target_type: TargetType
    target_id: int
    # 한 사람이 같은 대상을 두 번 신고할 수 없으므로(UniqueConstraint) 신고자 수와 같다.
    report_count: int
    # 사유별 내역. 많이 나온 순서다.
    reasons: list[ReportReasonCount]
    # 목록에 보여줄 짧은 미리보기. 신고 시점 사본을 잘라 만든다.
    preview: str
    # 판단에 필요한 전체 사본. 글이 지워져도 남아 있다.
    content: str
    # 원본이 이미 지워졌는지. 삭제 버튼을 감출지 판단하는 데 쓴다.
    is_deleted: bool
    # 정지 처분을 내리려면 대상이 아니라 작성자가 필요하다.
    author_id: int
    # 익명으로 쓴 글이면 None. 관리자 화면도 익명은 익명으로 보여준다.
    author_nickname: str | None
    # 모임 글이면 그 모임 id.
    group_id: int | None
    last_reported_at: datetime
    status: ReportStatus
    action: ReportAction | None
    handled_at: datetime | None
