from sqlalchemy import func

from sqlmodel import Session, col, select

from models.comment import Comment
from models.post import Post
from datetime import datetime, timezone

from models.report import Report, shorten_snapshot
from schemas.post import ContentType
from schemas.report import ReportAction, ReportReason, ReportStatus, TargetType

# 관리자 목록에서 보여줄 미리보기 길이. 사본은 원문 그대로 두고 볼 때만 자른다.
PREVIEW_LENGTH = 60


def _post_snapshot(session: Session, post: Post) -> str:
    """게시글을 한 덩어리 글로 만든다.

    제목만 남기면 관리자가 무엇이 문제인지 알 수 없어 본문까지 넣는다.
    사진은 파일이 지워질 수 있어 자리 표시만 남긴다.
    """
    assert post.id is not None
    from crud import post as post_crud

    parts = [post.title]
    for block in post_crud.get_post_blocks(session, post.id):
        parts.append("[사진]" if block.type == ContentType.IMAGE else block.content)
    return shorten_snapshot("\n".join(parts))


def report_post(
    session: Session, reporter_id: int, post: Post, reason: ReportReason
) -> bool:
    """게시글 신고. 이미 신고했으면 False."""
    assert post.id is not None
    if _already_reported(session, reporter_id, TargetType.POST, post.id):
        return False
    session.add(
        Report(
            reporter_id=reporter_id,
            target_type=TargetType.POST,
            target_id=post.id,
            reason=reason,
            target_content=_post_snapshot(session, post),
            target_author_id=post.author_id,
            target_author_nickname=post.author_nickname,
            target_group_id=post.group_id,
        )
    )
    session.commit()
    return True


def report_comment(
    session: Session, reporter_id: int, comment: Comment, reason: ReportReason
) -> bool:
    """댓글 신고. 이미 신고했으면 False."""
    assert comment.id is not None
    if _already_reported(session, reporter_id, TargetType.COMMENT, comment.id):
        return False

    # 댓글이 어느 모임 글에 달렸는지는 댓글만 봐서는 알 수 없다.
    post = session.get(Post, comment.post_id)
    session.add(
        Report(
            reporter_id=reporter_id,
            target_type=TargetType.COMMENT,
            target_id=comment.id,
            reason=reason,
            target_content=shorten_snapshot(comment.content),
            target_author_id=comment.author_id,
            target_author_nickname=comment.author_nickname,
            target_group_id=post.group_id if post else None,
        )
    )
    session.commit()
    return True


def _already_reported(
    session: Session, reporter_id: int, target_type: TargetType, target_id: int
) -> bool:
    return (
        session.exec(
            select(Report)
            .where(col(Report.reporter_id) == reporter_id)
            .where(col(Report.target_type) == target_type)
            .where(col(Report.target_id) == target_id)
        ).first()
        is not None
    )


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= PREVIEW_LENGTH:
        return text
    return text[:PREVIEW_LENGTH] + "…"


def _target_exists(session: Session, target_type: TargetType, target_id: int) -> bool:
    """대상이 아직 남아 있는지.

    답글이 달린 댓글은 지워도 행이 남고 내용만 비워지므로 그것도 사라진 것으로 본다.
    """
    if target_type == TargetType.POST:
        return session.get(Post, target_id) is not None
    comment = session.get(Comment, target_id)
    return comment is not None and bool(comment.content)


def count_reported_targets(
    session: Session, min_count: int, group_id: int | None = None
) -> int:
    """아직 처리하지 않은 신고 대상 수.

    group_id를 주면 그 모임 글의 신고만 센다. 모임장은 자기 모임 것만 본다.
    """
    statement = (
        select(col(Report.target_type), col(Report.target_id))
        .where(col(Report.status) == ReportStatus.PENDING)
        .group_by(col(Report.target_type), col(Report.target_id))
        .having(func.count() >= min_count)
    )
    if group_id is not None:
        statement = statement.where(col(Report.target_group_id) == group_id)

    # 세어야 하는 것은 행이 아니라 묶음의 개수다. COUNT를 바로 붙이면
    # GROUP BY 때문에 묶음마다 숫자가 하나씩 나온다. 서브쿼리로 감싼다.
    return session.exec(
        select(func.count()).select_from(statement.subquery())
    ).one()


def resolve_reports(
    session: Session,
    target_type: TargetType,
    target_id: int,
    admin_id: int,
    action: ReportAction,
) -> int:
    """이 대상의 미처리 신고를 모두 처리 완료로 바꾼다.

    신고 행을 지우지 않고 상태만 바꾼다. 나중에 같은 사람이 또 문제를
    일으켰을 때 앞서 어떤 처분을 했는지 볼 수 있어야 한다.
    """
    rows = session.exec(
        select(Report)
        .where(col(Report.target_type) == target_type)
        .where(col(Report.target_id) == target_id)
        .where(col(Report.status) == ReportStatus.PENDING)
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.status = ReportStatus.RESOLVED
        row.action = action
        row.handled_by = admin_id
        row.handled_at = now
        session.add(row)
    session.commit()
    return len(rows)


def get_pending_target(
    session: Session, target_type: TargetType, target_id: int
) -> Report | None:
    """이 대상의 미처리 신고 중 첫 건. 사본과 작성자를 읽는 데 쓴다."""
    return session.exec(
        select(Report)
        .where(col(Report.target_type) == target_type)
        .where(col(Report.target_id) == target_id)
        .where(col(Report.status) == ReportStatus.PENDING)
        .order_by(col(Report.created_at).asc())
    ).first()


def get_reported_targets(
    session: Session,
    min_count: int,
    skip: int = 0,
    limit: int = 20,
    target_type: TargetType | None = None,
    group_id: int | None = None,
) -> list[dict]:
    """min_count번 이상 신고된 대상들. 최근 신고순.

    신고를 낱개로 주면 같은 글이 신고당한 횟수만큼 목록에 반복되고, 관리자가
    그 글이 몇 명에게 신고됐는지 알 수 없다. 대상 단위로 묶어서 준다.
    """
    grouped_stmt = (
        select(
            col(Report.target_type),
            col(Report.target_id),
            func.count().label("cnt"),
            func.max(col(Report.created_at)).label("last"),
        )
        .where(col(Report.status) == ReportStatus.PENDING)
        .group_by(col(Report.target_type), col(Report.target_id))
        .having(func.count() >= min_count)
        .order_by(func.max(col(Report.created_at)).desc())
        .offset(skip)
        .limit(limit)
    )
    if target_type is not None:
        grouped_stmt = grouped_stmt.where(col(Report.target_type) == target_type)
    if group_id is not None:
        grouped_stmt = grouped_stmt.where(col(Report.target_group_id) == group_id)

    grouped = session.exec(grouped_stmt).all()
    if not grouped:
        return []

    items: list[dict] = []
    for t_type, t_id, count, last in grouped:
        rows = session.exec(
            select(Report)
            .where(col(Report.target_type) == t_type)
            .where(col(Report.target_id) == t_id)
            .where(col(Report.status) == ReportStatus.PENDING)
            .order_by(col(Report.created_at).asc())
        ).all()
        if not rows:
            continue

        # 사유별 건수를 많은 순으로.
        tally: dict[ReportReason, int] = {}
        for row in rows:
            tally[row.reason] = tally.get(row.reason, 0) + 1
        reasons = [
            {"reason": reason, "count": n}
            for reason, n in sorted(tally.items(), key=lambda kv: kv[1], reverse=True)
        ]

        first = rows[0]
        items.append(
            {
                "target_type": t_type,
                "target_id": t_id,
                "report_count": count,
                "reasons": reasons,
                # 첫 신고 때 사본을 남긴다. 글이 지워져도 이 값은 남아 있다.
                "preview": _shorten(first.target_content),
                "content": first.target_content,
                "author_id": first.target_author_id,
                "author_nickname": first.target_author_nickname,
                "group_id": first.target_group_id,
                "is_deleted": not _target_exists(session, t_type, t_id),
                "last_reported_at": last,
                "status": first.status,
                "action": first.action,
                "handled_at": first.handled_at,
            }
        )
    return items
