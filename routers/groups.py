from math import ceil

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlmodel import Session, col, select

from crud import group as group_crud
from crud import comment as comment_crud
from crud import post as post_crud
from crud import report as report_crud
from crud import upload as upload_crud
from crud import user as user_crud
from database import get_session
from dependencies import Pagination, get_current_user
from models import User
from models.user import KICKED_NICKNAME
from models import PostContent
from schemas import (
    ContentType,
    ReportAction,
    ReportedTarget,
    TargetType,
    PaginatedResponse,
    PostCreate,
    PostLikeResponse,
    NoticeUpdate,
    PostListResponse,
    PostResponse,
    PostUpdate,
)
from schemas.group import (
    ApplicationResponse,
    GroupSearchField,
    GroupCreate,
    GroupListResponse,
    GroupMemberResponse,
    GroupResponse,
    GroupUpdate,
    TransferLeaderRequest,
)
from services import group_leave
from utils.form_json import parse_form_json
from utils.image import delete_image, process_and_save_image

router = APIRouter(prefix="/groups", tags=["groups"])


def _get_group_or_404(session: Session, group_id: int):
    group = group_crud.get_group(session, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="모임을 찾을 수 없습니다")
    return group


def _require_leader(group, current_user: User):
    if group.leader_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="모임장만 수행할 수 있습니다")


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    group_data: str = Form(..., description="GroupCreate JSON 문자열"),
    cover_image: UploadFile | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 생성 (생성자가 자동으로 모임장)"""
    group_create = parse_form_json(GroupCreate, group_data)
    assert current_user.id is not None
    cover_image_url = None
    if cover_image:
        if cover_image.size:
            upload_crud.check_upload_limit(session, current_user.id, cover_image.size)
        cover_image_url, saved_size = process_and_save_image(cover_image, "group")
        upload_crud.log_upload(session, current_user.id, saved_size, cover_image_url)
    group = group_crud.create_group(session, current_user.id, group_create)
    if cover_image_url:
        group = group_crud.update_cover_image(session, group, cover_image_url)
    return group


@router.get("", response_model=PaginatedResponse[GroupListResponse])
def read_groups(
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 목록 조회"""
    groups = group_crud.get_groups(session, pagination.skip, pagination.size)
    total = group_crud.count_groups(session)
    assert current_user.id is not None
    return {
        "items": _group_list_items(session, groups, current_user.id),
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


def _group_detail(session: Session, group, current_user_id: int) -> dict:
    """단건 응답. 목록과 같은 값을 채워 화면이 동일하게 다룰 수 있게 한다."""
    assert group.id is not None
    counts = group_crud.get_member_count_map(session, [group.id])
    is_member = group_crud.is_member(session, current_user_id, group.id)

    # 공지는 모임 안의 글이므로 멤버에게만 준다. 가입 전에도 이름과 소개는
    # 볼 수 있어야 하지만 내부 글이 새어 나가면 안 된다.
    notice_post = None
    if is_member:
        notice = post_crud.get_group_notice(session, group.id)
        if notice is not None:
            notice_post = {"id": notice.id, "title": notice.title}

    return {
        **group.model_dump(),
        "member_count": counts.get(group.id, 0),
        "is_member": is_member,
        "notice_post": notice_post,
    }


def _member_items(session: Session, group, members: list) -> list[dict]:
    """멤버 목록에 닉네임과 프로필 사진을 붙인다."""
    users = {
        u.id: u
        for u in session.exec(
            select(User).where(col(User.id).in_([m.user_id for m in members]))
        ).all()
    } if members else {}

    return [
        {
            "user_id": m.user_id,
            "joined_at": m.joined_at,
            "nickname": users[m.user_id].nickname if m.user_id in users else "알 수 없음",
            "profile_pic": users[m.user_id].profile_pic if m.user_id in users else None,
            "is_leader": m.user_id == group.leader_id,
        }
        for m in members
    ]


def _application_items(session: Session, applications: list) -> list[dict]:
    """가입 신청 목록에 신청자 닉네임을 붙인다."""
    users = {
        u.id: u
        for u in session.exec(
            select(User).where(col(User.id).in_([a.user_id for a in applications]))
        ).all()
    } if applications else {}

    return [
        {
            **a.model_dump(),
            "nickname": users[a.user_id].nickname if a.user_id in users else None,
            "profile_pic": users[a.user_id].profile_pic if a.user_id in users else None,
        }
        for a in applications
    ]


def _group_list_items(
    session: Session, groups: list, current_user_id: int
) -> list[dict]:
    """목록 카드에 필요한 값만 담는다.

    멤버 수와 가입 여부는 모임마다 따로 조회하면 쿼리가 개수만큼 늘어나므로
    한 번씩만 읽어 사전으로 받아 쓴다.
    """
    group_ids = [g.id for g in groups if g.id is not None]
    counts = group_crud.get_member_count_map(session, group_ids)
    joined = group_crud.get_joined_group_ids(session, current_user_id, group_ids)

    return [
        {
            **g.model_dump(),
            "member_count": counts.get(g.id, 0),
            "is_member": g.id in joined,
        }
        for g in groups
    ]


@router.get("/my", response_model=PaginatedResponse[GroupListResponse])
def read_my_groups(
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내가 가입한 모임 목록"""
    assert current_user.id is not None
    groups = group_crud.get_my_groups(
        session, current_user.id, pagination.skip, pagination.size
    )
    total = group_crud.count_my_groups(session, current_user.id)
    return {
        "items": _group_list_items(session, groups, current_user.id),
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.get("/search", response_model=PaginatedResponse[GroupListResponse])
def search_groups(
    query: str,
    search_by: GroupSearchField = GroupSearchField.NAME,
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 검색 (이름 또는 소개글)"""
    assert current_user.id is not None
    groups = group_crud.search_groups(
        session, query, search_by, pagination.skip, pagination.size
    )
    total = group_crud.count_search_groups(session, query, search_by)
    return {
        "items": _group_list_items(session, groups, current_user.id),
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.get("/my-applications", response_model=list[ApplicationResponse])
def read_my_applications(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내 가입 신청 목록 및 결과 조회"""
    assert current_user.id is not None
    return _application_items(
        session, group_crud.get_applications_by_user(session, current_user.id)
    )


@router.get("/{group_id}", response_model=GroupResponse)
def read_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 상세 조회.

    가입 전에도 어떤 모임인지 보고 신청할 수 있어야 하므로 이름·소개·사진·
    멤버 수는 누구나 볼 수 있다. 모임 안의 글은 목록 조회에서 멤버만 받는다.
    """
    assert current_user.id is not None
    group = _get_group_or_404(session, group_id)
    return _group_detail(session, group, current_user.id)


@router.patch("/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: int,
    group_update: GroupUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 정보 수정 (모임장 전용)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    return group_crud.update_group(session, group, group_update)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 삭제 (모임장 전용)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    cover_image = group.cover_image
    group_crud.delete_group(session, group)
    if cover_image:
        upload_crud.delete_log_by_url(session, cover_image)
        delete_image(cover_image)


@router.put("/{group_id}/profile-pic", response_model=GroupResponse)
def upload_cover_image(
    group_id: int,
    file: UploadFile,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 소개사진 업로드 (모임장 전용)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    assert current_user.id is not None
    old_url = group.cover_image
    if file.size:
        upload_crud.check_upload_limit(session, current_user.id, file.size)
    url, saved_size = process_and_save_image(file, "group")
    upload_crud.log_upload(session, current_user.id, saved_size, url)
    result = group_crud.update_cover_image(session, group, url)
    if old_url:
        delete_image(old_url)
        upload_crud.delete_log_by_url(session, old_url)
    return result


@router.post("/{group_id}/apply", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply_to_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 가입 신청"""
    group = _get_group_or_404(session, group_id)
    if group.leader_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="모임장은 이미 멤버입니다"
        )
    assert current_user.id is not None
    result = group_crud.apply_to_group(session, current_user.id, group_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 멤버이거나 대기 중인 신청이 있습니다"
        )
    return result


@router.get("/{group_id}/applications", response_model=list[ApplicationResponse])
def read_applications(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """가입 신청 목록 조회 (모임장 전용)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    return _application_items(
        session, group_crud.get_pending_applications(session, group_id)
    )


@router.post("/{group_id}/applications/{application_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve_application(
    group_id: int,
    application_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """가입 신청 승인 (모임장 전용)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    application = group_crud.get_application(session, application_id)
    if not application or application.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청을 찾을 수 없습니다")
    if application.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="대기 중인 신청이 아닙니다")
    group_crud.approve_application(session, application)


@router.post("/{group_id}/applications/{application_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_application(
    group_id: int,
    application_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """가입 신청 거절 (모임장 전용)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    application = group_crud.get_application(session, application_id)
    if not application or application.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신청을 찾을 수 없습니다")
    if application.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="대기 중인 신청이 아닙니다")
    group_crud.reject_application(session, application)


@router.delete(
    "/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def kick_member(
    group_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임에서 멤버를 내보낸다.

    자기 자신을 지정하면 모임 탈퇴, 다른 사람을 지정하면 강퇴이며 강퇴는
    모임장만 할 수 있다. 어느 쪽이든 계정은 그대로 두고 그 모임에 남긴 글과
    댓글의 작성자 표시만 지운다.
    """
    group = _get_group_or_404(session, group_id)
    assert current_user.id is not None
    is_self = user_id == current_user.id
    if not is_self:
        _require_leader(group, current_user)

    if not group_crud.remove_member(session, group_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="모임 멤버가 아닙니다"
        )
    post_crud.update_group_posts_nickname(
        session, user_id, group_id, KICKED_NICKNAME
    )

    # 모임장이 나가면 남은 멤버 중 가장 먼저 가입한 사람에게 넘긴다.
    # 넘길 사람이 없으면 관리자가 없는 모임이 남으므로 모임을 삭제한다.
    if is_self and group.leader_id == user_id:
        group_leave.hand_over_or_delete(session, group, user_id)


@router.get("/{group_id}/members", response_model=list[GroupMemberResponse])
def read_members(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 멤버 목록 조회 (멤버 전용).

    누구나 볼 수 있으면 모임 id를 훑어 사용자 id와 닉네임 대응표를 모을 수
    있어 멤버에게만 공개한다.
    """
    group = _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    return _member_items(session, group, group_crud.get_members(session, group_id))


@router.post("/{group_id}/transfer", response_model=GroupResponse)
def transfer_leadership(
    group_id: int,
    body: TransferLeaderRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임장 인계 (모임장 전용, 대상은 현재 멤버여야 함)"""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    if body.new_leader_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="본인에게 인계할 수 없습니다"
        )
    if not group_crud.is_member(session, body.new_leader_id, group_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="해당 사용자는 모임 멤버가 아닙니다"
        )
    return group_crud.transfer_leadership(session, group, body.new_leader_id)


# ── 모임 게시글 ──────────────────────────────────────────


def _require_member(session: Session, user_id: int, group_id: int):
    if not group_crud.is_member(session, user_id, group_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="모임 멤버만 접근할 수 있습니다")


def _group_post_response(post, blocks: list[PostContent], current_user_id: int) -> dict:
    return {
        "id": post.id,
        "title": post.title,
        "author_nickname": post.author_nickname,
        "views": post.views,
        "likes": post.likes,
        "created_at": post.created_at,
        "is_edited": post.is_edited,
        "is_notice": post.is_notice,
        "blocks": [b.model_dump() for b in blocks],
        "is_mine": post.author_id == current_user_id,
    }


def _get_group_post_or_404(session: Session, group_id: int, post_id: int):
    post = post_crud.get_post(session, post_id)
    if not post or post.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="게시글을 찾을 수 없습니다")
    return post


@router.post("/{group_id}/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_group_post(
    group_id: int,
    post: PostCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 게시글 작성"""
    _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    if post.is_anonymous:
        # 모임은 서로 아는 사람들이 모인 곳이라 익명을 두지 않는다.
        # 수다 게시판에서는 그대로 익명을 쓸 수 있다.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="모임에서는 익명으로 작성할 수 없습니다",
        )
    author_nickname = current_user.nickname
    created_post = post_crud.create_post(session, post, current_user.id, author_nickname, group_id)
    assert created_post.id is not None
    blocks = post_crud.get_post_blocks(session, created_post.id)
    return _group_post_response(created_post, blocks, current_user.id)


@router.get("/{group_id}/posts", response_model=PaginatedResponse[PostResponse])
def read_group_posts(
    group_id: int,
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 게시글 목록 조회"""
    _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    blocked_ids = user_crud.get_blocked_user_ids(session, current_user.id)
    posts = post_crud.get_group_posts(session, group_id, pagination.skip, pagination.size, blocked_ids)
    total = post_crud.count_group_posts(session, group_id, blocked_ids)
    return {
        "items": [_group_post_response(p, post_crud.get_post_blocks(session, p.id), current_user.id) for p in posts],
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.get("/{group_id}/posts/{post_id}", response_model=PostResponse)
def read_group_post(
    group_id: int,
    post_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 게시글 조회"""
    _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    post = _get_group_post_or_404(session, group_id, post_id)
    post_crud.increment_views(session, post)
    assert post.id is not None
    blocks = post_crud.get_post_blocks(session, post.id)
    return _group_post_response(post, blocks, current_user.id)


@router.patch("/{group_id}/posts/{post_id}", response_model=PostResponse)
def update_group_post(
    group_id: int,
    post_id: int,
    post_update: PostUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 게시글 수정"""
    _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    post = _get_group_post_or_404(session, group_id, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="수정 권한이 없습니다")
    updated_post = post_crud.update_post(session, post, post_update)
    assert updated_post.id is not None
    blocks = post_crud.get_post_blocks(session, updated_post.id)
    return _group_post_response(updated_post, blocks, current_user.id)


@router.put("/{group_id}/posts/{post_id}/notice", response_model=PostResponse)
def set_group_post_notice(
    group_id: int,
    post_id: int,
    body: NoticeUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 공지 지정/해제.

    모임장만 바꿀 수 있다. 목록 맨 위를 차지하는 자리라 아무나 자기 글을
    올릴 수 있으면 안 된다. 대신 모임장은 남이 쓴 좋은 안내글도 공지로
    올릴 수 있어야 하므로 글쓴이는 따지지 않는다.

    공지는 모임당 하나다. 새로 지정하면 이전 공지는 자동으로 풀린다.
    """
    group = _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_leader(group, current_user)
    post = _get_group_post_or_404(session, group_id, post_id)
    updated = post_crud.set_group_notice(session, post, body.is_notice)
    assert updated.id is not None
    blocks = post_crud.get_post_blocks(session, updated.id)
    return _group_post_response(updated, blocks, current_user.id)


@router.delete("/{group_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group_post(
    group_id: int,
    post_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 게시글 삭제"""
    _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    post = _get_group_post_or_404(session, group_id, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="삭제 권한이 없습니다")
    assert post.id is not None
    blocks = post_crud.get_post_blocks(session, post.id)
    image_urls = [b.content for b in blocks if b.type == ContentType.IMAGE]
    post_crud.delete_post(session, post)
    for url in image_urls:
        upload_crud.delete_log_by_url(session, url)
        delete_image(url)


@router.post("/{group_id}/posts/{post_id}/like", response_model=PostLikeResponse)
def toggle_like_group_post(
    group_id: int,
    post_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 게시글 좋아요 토글"""
    _get_group_or_404(session, group_id)
    assert current_user.id is not None
    _require_member(session, current_user.id, group_id)
    post = _get_group_post_or_404(session, group_id, post_id)
    if post.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인의 게시글에는 좋아요를 누를 수 없습니다",
        )
    post, liked = post_crud.toggle_like(session, post, current_user.id)
    assert post.id is not None
    blocks = post_crud.get_post_blocks(session, post.id)
    return {**_group_post_response(post, blocks, current_user.id), "liked": liked}


# 모임은 아는 사람끼리 모인 곳이라 신고 한 건도 의미가 있다. 관리자 목록처럼
# 2회 이상을 요구하면 작은 모임에서는 아무것도 올라오지 않는다.
GROUP_MIN_REPORT_COUNT = 1


def _leader_report_or_404(
    session: Session, group_id: int, target_type: TargetType, target_id: int
):
    """이 모임에 속한 미처리 신고인지 확인하고 첫 건을 돌려준다.

    target_group_id를 함께 보는 이유는, 모임장이 경로만 바꿔서 남의 모임
    신고를 건드리지 못하게 하기 위해서다.
    """
    report = report_crud.get_pending_target(session, target_type, target_id)
    if report is None or report.target_group_id != group_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="처리할 신고가 없습니다"
        )
    return report


@router.get("/{group_id}/reports", response_model=PaginatedResponse[ReportedTarget])
def read_group_reports(
    group_id: int,
    pagination: Pagination = Depends(),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """모임 안에서 신고된 글·댓글 목록. 모임장만 볼 수 있다."""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    items = report_crud.get_reported_targets(
        session,
        GROUP_MIN_REPORT_COUNT,
        skip=pagination.skip,
        limit=pagination.size,
        group_id=group_id,
    )
    total = report_crud.count_reported_targets(
        session, GROUP_MIN_REPORT_COUNT, group_id=group_id
    )
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
    }


@router.delete(
    "/{group_id}/reports/{target_type}/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_reported_content(
    group_id: int,
    target_type: TargetType,
    target_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """신고된 글이나 댓글을 모임장이 지운다."""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    assert current_user.id is not None
    _leader_report_or_404(session, group_id, target_type, target_id)

    if target_type == TargetType.POST:
        post = post_crud.get_post(session, target_id)
        if post:
            post_crud.delete_post(session, post)
    else:
        comment = comment_crud.get_comment(session, target_id)
        if comment:
            comment_crud.delete_comment(session, comment)

    report_crud.resolve_reports(
        session, target_type, target_id, current_user.id, ReportAction.DELETED
    )


@router.post(
    "/{group_id}/reports/{target_type}/{target_id}/kick",
    status_code=status.HTTP_204_NO_CONTENT,
)
def kick_reported_author(
    group_id: int,
    target_type: TargetType,
    target_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """신고된 글의 작성자를 강퇴하고 그 글도 지운다.

    글을 남겨두면 강퇴한 사람의 글이 모임에 계속 남는다. 관리자의 계정 정지와
    같은 이유로 서버에서 묶어 처리한다.

    모임장이 할 수 있는 것은 여기까지다. 계정 정지는 앱 전체에 영향을 주므로
    관리자만 한다.
    """
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    assert current_user.id is not None
    report = _leader_report_or_404(session, group_id, target_type, target_id)

    if report.target_author_id == group.leader_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="모임장은 강퇴할 수 없습니다",
        )

    # 이미 나간 사람일 수 있다. 그래도 글은 지우고 신고는 처리한다.
    if group_crud.remove_member(session, group_id, report.target_author_id):
        post_crud.update_group_posts_nickname(
            session, report.target_author_id, group_id, KICKED_NICKNAME
        )

    if target_type == TargetType.POST:
        post = post_crud.get_post(session, target_id)
        if post:
            post_crud.delete_post(session, post)
    else:
        comment = comment_crud.get_comment(session, target_id)
        if comment:
            comment_crud.delete_comment(session, comment)

    report_crud.resolve_reports(
        session, target_type, target_id, current_user.id, ReportAction.KICKED
    )


@router.post(
    "/{group_id}/reports/{target_type}/{target_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
def dismiss_group_report(
    group_id: int,
    target_type: TargetType,
    target_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """문제가 없다고 판단해 신고를 넘긴다. 글은 그대로 둔다."""
    group = _get_group_or_404(session, group_id)
    _require_leader(group, current_user)
    assert current_user.id is not None
    _leader_report_or_404(session, group_id, target_type, target_id)
    report_crud.resolve_reports(
        session, target_type, target_id, current_user.id, ReportAction.DISMISSED
    )
