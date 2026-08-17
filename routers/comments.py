from math import ceil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from crud import comment as comment_crud
from crud import group as group_crud
from crud import post as post_crud
from crud import report as report_crud
from crud import user as user_crud
from database import get_session
from dependencies import Pagination, get_current_user
from models import User
from schemas import (
    CommentCreate,
    CommentLikeResponse,
    CommentResponse,
    CommentUpdate,
    PaginatedResponse,
    ReportCreate,
)
from services.rate_limit import check_rate_limit

router = APIRouter(tags=["comments"])

COMMENT_RATE_COOLDOWN_SECONDS = 3
MAX_COMMENTS_PER_WINDOW = 50
COMMENT_RATE_WINDOW_SECONDS = 10 * 60


def _check_group_post_access(session, post, user_id: int):
    if post.group_id and not group_crud.is_member(session, user_id, post.group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="모임 멤버만 접근할 수 있습니다"
        )


def _reject_anonymous_in_group(post, is_anonymous: bool) -> None:
    """모임 글에는 익명 댓글을 달 수 없다. 수다 게시판은 그대로 허용한다.

    is_anonymous 필드는 두 게시판이 함께 쓰는 스키마에 있어 없앨 수가 없다.
    조용히 실명으로 바꾸는 대신 거절하는 이유는, 화면 쪽에서 익명 토글이
    다시 딸려 들어오는 실수를 바로 드러내기 위해서다.
    """
    if post.group_id and is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="모임에서는 익명으로 작성할 수 없습니다",
        )


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    post_id: int,
    comment: CommentCreate,
    parent_id: int | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글에 댓글 작성"""
    post = post_crud.get_post(session, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="게시글을 찾을 수 없습니다"
        )
    assert current_user.id is not None
    _check_group_post_access(session, post, current_user.id)
    _reject_anonymous_in_group(post, comment.is_anonymous)
    check_rate_limit(
        f"comment_rate:{current_user.id}",
        cooldown_seconds=COMMENT_RATE_COOLDOWN_SECONDS,
        max_count=MAX_COMMENTS_PER_WINDOW,
        window_seconds=COMMENT_RATE_WINDOW_SECONDS,
        cooldown_message="{wait}초 후 다시 시도해주세요",
        limit_message="댓글 작성 횟수를 초과했습니다. 잠시 후 다시 시도해주세요",
    )
    author_nickname = None if comment.is_anonymous else current_user.nickname
    result = comment_crud.create_comment(
        session, comment, current_user.id, post_id, author_nickname, parent_id
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="올바르지 않은 parent_id입니다",
        )
    # 방금 본인이 쓴 댓글이므로 is_mine은 항상 참이다.
    return {**result.model_dump(), "is_mine": True}


@router.get(
    "/posts/{post_id}/comments", response_model=PaginatedResponse[CommentResponse]
)
def read_comments(
    post_id: int,
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글의 댓글 목록 조회"""
    post = post_crud.get_post(session, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="게시글을 찾을 수 없습니다"
        )
    assert current_user.id is not None
    _check_group_post_access(session, post, current_user.id)
    blocked_ids = user_crud.get_blocked_user_ids(session, current_user.id)
    comments = comment_crud.get_comments_by_post(session, post_id, pagination.skip, pagination.size)
    total = comment_crud.count_comments_by_post(session, post_id)
    anon_order = comment_crud.get_anon_order(session, post_id)

    return {
        "items": [
            {
                "id": c.id,
                "content": c.content,
                "author_nickname": f"익명{anon_order[c.author_id]}" if c.author_nickname is None else c.author_nickname,
                "post_id": c.post_id,
                "parent_id": c.parent_id,
                "likes": c.likes,
                "created_at": c.created_at,
                "is_edited": c.is_edited,
                "is_blocked": c.author_id in blocked_ids,
                "is_mine": c.author_id == current_user.id,
            }
            for c in comments
        ],
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
def update_comment(
    comment_id: int,
    comment_update: CommentUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """댓글 수정"""
    comment = comment_crud.get_comment(session, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="댓글을 찾을 수 없습니다"
        )
    if comment.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="수정 권한이 없습니다"
        )
    # 수정하면서 익명으로 바꾸는 길도 함께 막는다.
    post = post_crud.get_post(session, comment.post_id)
    if post:
        _reject_anonymous_in_group(post, comment_update.is_anonymous)
    # 작성자만 여기 도달하므로 is_mine은 항상 참이다.
    updated = comment_crud.update_comment(session, comment, comment_update)
    return {**updated.model_dump(), "is_mine": True}


@router.post("/comments/{comment_id}/like", response_model=CommentLikeResponse)
def toggle_like_comment(
    comment_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """댓글 좋아요 토글"""
    comment = comment_crud.get_comment(session, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="댓글을 찾을 수 없습니다"
        )
    if comment.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인의 댓글에는 좋아요를 누를 수 없습니다",
        )
    assert current_user.id is not None
    post = post_crud.get_post(session, comment.post_id)
    if post:
        _check_group_post_access(session, post, current_user.id)
    comment, liked = comment_crud.toggle_like(session, comment, current_user.id)
    return {
        "id": comment.id,
        "content": comment.content,
        "author_nickname": comment.author_nickname,
        "post_id": comment.post_id,
        "parent_id": comment.parent_id,
        "likes": comment.likes,
        "created_at": comment.created_at,
        "is_edited": comment.is_edited,
        "is_blocked": False,
        "is_mine": comment.author_id == current_user.id,
        "liked": liked,
    }


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """댓글 삭제"""
    comment = comment_crud.get_comment(session, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="댓글을 찾을 수 없습니다"
        )
    if comment.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="삭제 권한이 없습니다"
        )
    comment_crud.delete_comment(session, comment)


@router.post("/comments/{comment_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_comment(
    comment_id: int,
    body: ReportCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """댓글 신고"""
    comment = comment_crud.get_comment(session, comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="댓글을 찾을 수 없습니다"
        )
    if comment.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="본인의 댓글은 신고할 수 없습니다"
        )
    assert current_user.id is not None
    if not report_crud.report_comment(session, current_user.id, comment, body.reason):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 신고한 댓글입니다"
        )
