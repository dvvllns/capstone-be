from math import ceil

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel import Session

from crud import post as post_crud
from crud import report as report_crud
from crud import upload as upload_crud
from crud import user as user_crud
from database import get_session
from dependencies import Pagination, get_current_user
from models import Post, PostContent, User
from schemas import (
    ContentType,
    PaginatedResponse,
    PostCreate,
    PostLikeResponse,
    PostListResponse,
    PostResponse,
    PostUpdate,
    ReportCreate,
)
from schemas.post import PostSearchField
from services.rate_limit import check_rate_limit
from utils.image import delete_image, process_and_save_image

router = APIRouter(prefix="/posts", tags=["posts"])

POST_RATE_COOLDOWN_SECONDS = 10
MAX_POSTS_PER_WINDOW = 20
POST_RATE_WINDOW_SECONDS = 10 * 60


@router.post("/images")
def upload_image(
    file: UploadFile,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글용 이미지 업로드"""
    assert current_user.id is not None
    if file.size and not upload_crud.check_upload_limit(
        session, current_user.id, file.size
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="10분간 업로드 한도(100MB)를 초과했습니다",
        )
    url, saved_size = process_and_save_image(file, "post")
    upload_crud.log_upload(session, current_user.id, saved_size, url)
    return {"url": url}


def _post_response(
    post: Post, blocks: list[PostContent], current_user_id: int
) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "author_nickname": post.author_nickname,
        "views": post.views,
        "likes": post.likes,
        "created_at": post.created_at,
        "is_edited": post.is_edited,
        "blocks": [b.model_dump() for b in blocks],
        "is_mine": post.author_id == current_user_id,
    }


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    post: PostCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 작성"""
    assert current_user.id is not None
    check_rate_limit(
        f"post_rate:{current_user.id}",
        cooldown_seconds=POST_RATE_COOLDOWN_SECONDS,
        max_count=MAX_POSTS_PER_WINDOW,
        window_seconds=POST_RATE_WINDOW_SECONDS,
        cooldown_message="{wait}초 후 다시 시도해주세요",
        limit_message="게시글 작성 횟수를 초과했습니다. 잠시 후 다시 시도해주세요",
    )
    author_nickname = None if post.is_anonymous else current_user.nickname
    created_post = post_crud.create_post(
        session, post, current_user.id, author_nickname
    )
    assert created_post.id is not None
    blocks = post_crud.get_post_blocks(session, created_post.id)
    return _post_response(created_post, blocks, current_user.id)


PREVIEW_MAX_LENGTH = 100


def _post_list_items(session: Session, posts: list[Post]) -> list[dict]:
    """목록 카드에 필요한 값만 담은 항목들.

    미리보기와 댓글 수는 게시글마다 조회하면 쿼리가 개수만큼 늘어나므로
    한 번씩만 읽어 사전으로 받아 쓴다.
    """
    post_ids = [p.id for p in posts if p.id is not None]
    previews = post_crud.get_preview_map(session, post_ids)
    comment_counts = post_crud.get_comment_count_map(session, post_ids)

    items = []
    for p in posts:
        preview = previews.get(p.id)
        if preview and len(preview) > PREVIEW_MAX_LENGTH:
            preview = preview[:PREVIEW_MAX_LENGTH]
        items.append(
            {
                "id": p.id,
                "title": p.title,
                "author_nickname": p.author_nickname,
                "views": p.views,
                "likes": p.likes,
                "created_at": p.created_at,
                "preview": preview,
                "comment_count": comment_counts.get(p.id, 0),
            }
        )
    return items


@router.get("", response_model=PaginatedResponse[PostListResponse])
def read_posts(
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 목록 조회"""
    assert current_user.id is not None
    blocked_ids = user_crud.get_blocked_user_ids(session, current_user.id)
    posts = post_crud.get_posts(session, pagination.skip, pagination.size, blocked_ids)
    total = post_crud.count_posts(session, blocked_author_ids=blocked_ids)

    return {
        "items": _post_list_items(session, posts),
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.get("/search", response_model=PaginatedResponse[PostListResponse])
def search_posts(
    query: str,
    search_by: PostSearchField,
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 검색"""
    assert current_user.id is not None
    blocked_ids = user_crud.get_blocked_user_ids(session, current_user.id)
    posts = post_crud.search_posts(
        session, query, search_by, pagination.skip, pagination.size, blocked_ids
    )
    total = post_crud.count_search_posts(session, query, search_by, blocked_ids)

    return {
        "items": _post_list_items(session, posts),
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


def _get_general_post_or_404(session: Session, post_id: int):
    post = post_crud.get_post(session, post_id)
    if not post or post.group_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="게시글을 찾을 수 없습니다")
    return post


@router.get("/{post_id}", response_model=PostResponse)
def read_post(
    post_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 조회"""
    post = _get_general_post_or_404(session, post_id)
    post_crud.increment_views(session, post)
    assert post.id is not None
    assert current_user.id is not None
    blocks = post_crud.get_post_blocks(session, post.id)
    return _post_response(post, blocks, current_user.id)


@router.patch("/{post_id}", response_model=PostResponse)
def update_post(
    post_id: int,
    post_update: PostUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 수정"""
    post = _get_general_post_or_404(session, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="수정 권한이 없습니다"
        )
    updated_post = post_crud.update_post(session, post, post_update)
    assert updated_post.id is not None
    blocks = post_crud.get_post_blocks(session, updated_post.id)
    return _post_response(updated_post, blocks, current_user.id)


@router.post("/{post_id}/like", response_model=PostLikeResponse)
def toggle_like_post(
    post_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 좋아요 토글"""
    post = _get_general_post_or_404(session, post_id)
    if post.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인의 게시글에는 좋아요를 누를 수 없습니다",
        )
    assert current_user.id is not None
    post, liked = post_crud.toggle_like(session, post, current_user.id)
    assert post.id is not None
    blocks = post_crud.get_post_blocks(session, post.id)
    return {**_post_response(post, blocks, current_user.id), "liked": liked}


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 삭제"""
    post = _get_general_post_or_404(session, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="삭제 권한이 없습니다"
        )
    assert post.id is not None
    blocks = post_crud.get_post_blocks(session, post.id)
    image_urls = [b.content for b in blocks if b.type == ContentType.IMAGE]
    post_crud.delete_post(session, post)
    for url in image_urls:
        delete_image(url)
        upload_crud.delete_log_by_url(session, url)


@router.post("/{post_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_post(
    post_id: int,
    body: ReportCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """게시글 신고"""
    post = post_crud.get_post(session, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="게시글을 찾을 수 없습니다"
        )
    if post.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="본인의 게시글은 신고할 수 없습니다"
        )
    assert current_user.id is not None
    if not report_crud.report_post(session, current_user.id, post, body.reason):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 신고한 게시글입니다"
        )
