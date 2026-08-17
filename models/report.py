from datetime import datetime, timezone

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import AutoString, Field, SQLModel

from schemas.report import ReportAction, ReportReason, ReportStatus, TargetType

# 사본으로 남길 본문 길이 상한. 판단에 필요한 만큼만 남기고 자른다.
SNAPSHOT_MAX_LENGTH = 1000


class Report(SQLModel, table=True):
    """게시글·댓글 신고 한 건.

    게시글용과 댓글용을 나누지 않는 이유는, 관리자가 둘을 한 목록에서 보고
    처리하기 때문이다. 테이블이 둘이면 정렬과 페이지를 파이썬에서 손으로
    맞춰야 하고, 나중에 붙는 컬럼을 매번 두 번씩 넣게 된다.

    target_id에 외래키를 걸지 않은 것은 일부러다. 외래키를 걸면 글이 지워질 때
    신고 행도 함께 사라져서, 신고당한 사람이 먼저 지우면 관리자가 그런 신고가
    있었다는 사실조차 알 수 없다.
    """

    __tablename__ = "report"
    # 한 사람이 같은 대상을 여러 번 신고해 숫자를 부풀리지 못하게 한다.
    __table_args__ = (
        UniqueConstraint("reporter_id", "target_type", "target_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    reporter_id: int = Field(foreign_key="user.id")

    target_type: TargetType = Field(sa_type=AutoString())
    # 대상이 지워져도 어떤 대상이었는지는 남는다. 같은 대상의 신고를 묶는 데 쓴다.
    target_id: int
    reason: ReportReason = Field(sa_type=AutoString())

    # ── 신고 시점 사본 ───────────────────────────────────────────────
    # 신고한 사람이 무엇을 보고 신고했는지 그대로 남긴다. 글을 고쳐서
    # 빠져나가는 것도 이 값과 비교하면 드러난다.
    target_content: str = Field(max_length=SNAPSHOT_MAX_LENGTH)
    # 글이 사라진 뒤에도 누구를 정지할지 알아야 한다.
    target_author_id: int = Field(foreign_key="user.id")
    # 그 글에 보이던 이름. 익명으로 쓴 글이면 None이고, 관리자 화면도 익명으로
    # 보여준다. 조치는 target_author_id로 한다.
    target_author_nickname: str | None = None
    # 모임 글이면 그 모임. 나중에 모임장에게 넘길 때 쓴다.
    target_group_id: int | None = Field(default=None, foreign_key="groups.id")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )

    # ── 처리 ─────────────────────────────────────────────────────────
    # 처리한 신고를 지우지 않고 상태만 바꾸는 이유는, 나중에 같은 사람이
    # 또 문제를 일으켰을 때 앞선 처분을 확인할 수 있어야 하기 때문이다.
    status: ReportStatus = Field(default=ReportStatus.PENDING, sa_type=AutoString())
    action: ReportAction | None = Field(default=None, sa_type=AutoString(), nullable=True)
    handled_by: int | None = Field(default=None, foreign_key="user.id")
    handled_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True), nullable=True
    )


def shorten_snapshot(text: str) -> str:
    """사본 본문을 상한에 맞춰 자른다."""
    if len(text) <= SNAPSHOT_MAX_LENGTH:
        return text
    return text[: SNAPSHOT_MAX_LENGTH - 1] + "…"
