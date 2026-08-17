from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from crud import comment as comment_crud
from crud import post as post_crud
from crud import report as report_crud
from crud import user as user_crud
from database import get_session
from dependencies import get_admin_user
from models import User
from dependencies import Pagination
from schemas import (
    AdminStats,
    PaginatedResponse,
    ReportAction,
    ReportedTarget,
    SuspendUserRequest,
    TargetType,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_post(
    post_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """게시글 강제 삭제"""
    post = post_crud.get_post(session, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="게시글을 찾을 수 없습니다"
        )
    assert admin.id is not None
    post_crud.delete_post(session, post)
    # 지웠으면 그 신고는 볼 일이 끝났다. 목록에서 내려간다.
    report_crud.resolve_reports(
        session, TargetType.POST, post_id, admin.id, ReportAction.DELETED
    )


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_comment(
    comment_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """댓글 강제 삭제"""
    comment = comment_crud.get_comment(session, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="댓글을 찾을 수 없습니다"
        )
    assert admin.id is not None
    comment_crud.delete_comment(session, comment)
    report_crud.resolve_reports(
        session, TargetType.COMMENT, comment_id, admin.id, ReportAction.DELETED
    )


@router.post("/user/{user_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
def suspend_user(
    user_id: int,
    body: SuspendUserRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """사용자 계정 정지"""
    user = user_crud.get_user(session, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 계정은 정지할 수 없습니다",
        )
    user_crud.suspend_user(session, user, body.days)


# 한두 사람의 신고만으로 관리자 화면에 올리면 마음에 안 드는 글을 신고하는
# 것만으로 남의 글을 목록에 올릴 수 있다. 서로 다른 사람이 여러 번 신고한
# 것만 본다.
DEFAULT_MIN_REPORT_COUNT = 2


@router.get("/reports", response_model=PaginatedResponse[ReportedTarget])
def get_reports(
    target_type: TargetType | None = None,
    min_count: int = Query(
        default=DEFAULT_MIN_REPORT_COUNT,
        ge=1,
        description="이 횟수 이상 신고된 것만 보여준다",
    ),
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """신고 누적된 게시글·댓글 목록.

    신고를 낱개로 주면 같은 글이 신고당한 횟수만큼 목록에 반복되고, 관리자가
    그 글이 몇 명에게 신고됐는지 알 수 없다. 대상 단위로 묶어서 준다.
    """
    items = report_crud.get_reported_targets(
        session,
        min_count,
        skip=pagination.skip,
        limit=pagination.size,
        target_type=target_type,
    )
    total = report_crud.count_reported_targets(session, min_count)

    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.get("/stats", response_model=AdminStats)
def get_stats(
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """관리자 화면 상단 요약.

    신고 목록과 따로 두는 이유는, 정지 인원이 신고와 무관하게 바뀌고
    목록을 넘길 때마다 다시 셀 필요가 없기 때문이다.
    """
    return {
        "pending_reports": report_crud.count_reported_targets(
            session, DEFAULT_MIN_REPORT_COUNT
        ),
        "suspended_users": user_crud.count_suspended_users(session),
    }


@router.post(
    "/reports/{target_type}/{target_id}/suspend",
    status_code=status.HTTP_204_NO_CONTENT,
)
def suspend_from_report(
    target_type: TargetType,
    target_id: int,
    body: SuspendUserRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """신고된 글의 작성자를 정지하고, 그 글도 함께 지운다.

    정지만 하고 글을 남겨두면 정지 기간에도 문제된 글이 그대로 보인다.
    정지할 만한 글이면 지울 글이기도 하므로 서버에서 묶어서 처리한다.

    글이 이미 지워졌어도 정지는 할 수 있다. 작성자가 먼저 지우고 빠져나가는
    것을 막기 위해 신고에 사본을 남겨두고 있다.
    """
    assert admin.id is not None
    report = report_crud.get_pending_target(session, target_type, target_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="처리할 신고가 없습니다"
        )

    author = user_crud.get_user(session, report.target_author_id)
    if not author:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="작성자를 찾을 수 없습니다"
        )
    if author.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 계정은 정지할 수 없습니다",
        )
    # 탈퇴한 계정은 정지해도 아무 일이 일어나지 않는다. 관리자가 처분했다고
    # 착각하지 않도록 막고, 글만 지우도록 안내한다.
    if author.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="탈퇴한 계정은 정지할 수 없습니다. 강제 삭제만 할 수 있습니다",
        )

    user_crud.suspend_user(session, author, body.days)

    if target_type == TargetType.POST:
        post = post_crud.get_post(session, target_id)
        if post:
            post_crud.delete_post(session, post)
    else:
        comment = comment_crud.get_comment(session, target_id)
        if comment:
            comment_crud.delete_comment(session, comment)

    report_crud.resolve_reports(
        session, target_type, target_id, admin.id, ReportAction.SUSPENDED
    )


@router.post(
    "/reports/{target_type}/{target_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
def dismiss_report(
    target_type: TargetType,
    target_id: int,
    session: Session = Depends(get_session),
    admin: User = Depends(get_admin_user),
):
    """문제가 없다고 판단해 신고를 넘긴다. 글은 그대로 둔다.

    이게 없으면 관리자가 부당한 신고라고 봐도 삭제나 정지 말고는 목록에서
    내릴 방법이 없어, 처리할 수 없는 신고가 계속 쌓인다.
    """
    assert admin.id is not None
    if report_crud.get_pending_target(session, target_type, target_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="처리할 신고가 없습니다"
        )
    report_crud.resolve_reports(
        session, target_type, target_id, admin.id, ReportAction.DISMISSED
    )
