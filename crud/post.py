from sqlalchemy import func
from sqlmodel import Session, col, select, update

from crud import upload as upload_crud
from models import Comment, Post, PostContent, PostLike, User
from schemas import ContentType, PostCreate, PostSearchField, PostUpdate
from utils.image import delete_image


def create_post(
    session: Session,
    post_create: PostCreate,
    author_id: int,
    author_nickname: str | None,
    group_id: int | None = None,
) -> Post:
    """게시글 작성"""
    post = Post(
        title=post_create.title,
        author_id=author_id,
        author_nickname=author_nickname,
        group_id=group_id,
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    assert post.id is not None
    for block in post_create.blocks:
        session.add(
            PostContent(
                post_id=post.id,
                order=block.order,
                type=block.type,
                content=block.content,
            )
        )
    session.commit()
    return post


def get_posts(
    session: Session,
    skip: int = 0,
    limit: int = 10,
    blocked_author_ids: set[int] | None = None,
) -> list[Post]:
    """게시글 목록 조회 (모임 게시글 제외)"""
    statement = (
        select(Post)
        .where(col(Post.group_id).is_(None))
        .order_by(col(Post.created_at).desc())
    )
    if blocked_author_ids:
        statement = statement.where(col(Post.author_id).notin_(blocked_author_ids))
    return list(session.exec(statement.offset(skip).limit(limit)).all())


def get_group_posts(
    session: Session,
    group_id: int,
    skip: int = 0,
    limit: int = 10,
    blocked_author_ids: set[int] | None = None,
) -> list[Post]:
    """모임 게시글 목록 조회. 공지는 뺀다.

    공지는 모임 상세 응답에 따로 실어 배너로 보여준다. 목록에 섞어 보내면
    공지가 첫 페이지 한 칸을 먹어 페이지마다 글 개수가 달라진다.
    """
    statement = (
        select(Post)
        .where(col(Post.group_id) == group_id)
        .where(col(Post.is_notice).is_(False))
        .order_by(col(Post.created_at).desc())
    )
    if blocked_author_ids:
        statement = statement.where(col(Post.author_id).notin_(blocked_author_ids))
    return list(session.exec(statement.offset(skip).limit(limit)).all())


def get_post(session: Session, id: int) -> Post | None:
    """게시글 조회"""
    return session.get(Post, id)


def get_post_blocks(session: Session, post_id: int) -> list[PostContent]:
    """게시글 콘텐츠 블록 조회 (순서대로)"""
    statement = (
        select(PostContent)
        .where(PostContent.post_id == post_id)
        .order_by(col(PostContent.order).asc())
    )
    return list(session.exec(statement).all())


def update_post(session: Session, post: Post, post_update: PostUpdate) -> Post:
    """게시글 수정. blocks 교체 시 더 이상 쓰이지 않는 이미지 파일은 삭제한다."""
    if post_update.title is not None:
        post.title = post_update.title
    if post_update.blocks is not None:
        assert post.id is not None
        existing = session.exec(
            select(PostContent).where(PostContent.post_id == post.id)
        ).all()
        old_image_urls = {b.content for b in existing if b.type == ContentType.IMAGE}
        new_image_urls = {
            b.content for b in post_update.blocks if b.type == ContentType.IMAGE
        }
        for block in existing:
            session.delete(block)
        for block in post_update.blocks:
            session.add(
                PostContent(
                    post_id=post.id,
                    order=block.order,
                    type=block.type,
                    content=block.content,
                )
            )
        for url in old_image_urls - new_image_urls:
            upload_crud.delete_log_by_url(session, url)
            delete_image(url)
    post.is_edited = True
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def delete_post(session: Session, post: Post) -> None:
    """게시글 삭제"""
    session.delete(post)
    session.commit()


def increment_views(session: Session, post: Post) -> Post:
    """조회수 1 증가"""
    post.views += 1
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def toggle_like(session: Session, post: Post, user_id: int) -> tuple[Post, bool]:
    """좋아요 토글. (Post, liked 여부) 반환"""
    assert post.id is not None
    like = session.get(PostLike, (post.id, user_id))
    if like:
        session.delete(like)
        post.likes -= 1
        liked = False
    else:
        session.add(PostLike(post_id=post.id, user_id=user_id))
        post.likes += 1
        liked = True
    session.add(post)
    session.commit()
    session.refresh(post)
    return post, liked


def update_group_posts_nickname(
    session: Session, author_id: int, group_id: int, new_nickname: str
) -> None:
    """게시글/댓글의 작성자 표시를 한 모임 범위에서만 바꾼다.

    모임 탈퇴·강퇴 시 그 모임에 남긴 글을 익명 처리하는 데 쓴다. 계정 자체는
    그대로이고 다른 모임이나 수다 글에는 영향이 없다. 익명으로 쓴 글
    (author_nickname이 None)은 원래 작성자가 드러나지 않으므로 건드리지 않는다.

    범위 제한이 없는 update_posts_nickname과 짝을 이룬다.
    """
    session.exec(
        update(Post)
        .where(col(Post.author_id) == author_id)
        .where(col(Post.group_id) == group_id)
        .where(col(Post.author_nickname).is_not(None))
        .values(author_nickname=new_nickname)
    )
    # 댓글은 group_id를 갖고 있지 않아 해당 모임 게시글에 달린 것만 고른다.
    group_post_ids = select(Post.id).where(col(Post.group_id) == group_id)
    session.exec(
        update(Comment)
        .where(col(Comment.author_id) == author_id)
        .where(col(Comment.post_id).in_(group_post_ids))
        .where(col(Comment.author_nickname).is_not(None))
        .values(author_nickname=new_nickname)
    )
    session.commit()


def update_posts_nickname(session: Session, author_id: int, new_nickname: str) -> None:
    """닉네임 변경 시 해당 유저의 모든 게시글 author_nickname 동기화"""
    session.exec(
        update(Post)
        .where(col(Post.author_id) == author_id)
        .where(col(Post.author_nickname).is_not(None))
        .values(author_nickname=new_nickname)
    )
    session.commit()


def get_preview_map(session: Session, post_ids: list[int]) -> dict[int, str]:
    """게시글 id -> 본문 미리보기.

    목록에서 게시글마다 블록을 따로 읽으면 쿼리가 개수만큼 늘어나므로
    한 번에 읽어 사전으로 만든다. 본문 텍스트는 order가 가장 앞인 text 블록
    하나뿐이다(스키마 검증으로 보장).
    """
    if not post_ids:
        return {}

    statement = (
        select(PostContent)
        .where(col(PostContent.post_id).in_(post_ids))
        .where(col(PostContent.type) == ContentType.TEXT)
        .order_by(col(PostContent.post_id), col(PostContent.order).asc())
    )
    preview: dict[int, str] = {}
    for block in session.exec(statement).all():
        preview.setdefault(block.post_id, block.content)
    return preview


def get_comment_count_map(session: Session, post_ids: list[int]) -> dict[int, int]:
    """게시글 id -> 댓글 수(답글 포함). 한 번의 집계 쿼리로 구한다."""
    if not post_ids:
        return {}

    statement = (
        select(Comment.post_id, func.count())
        .where(col(Comment.post_id).in_(post_ids))
        .group_by(col(Comment.post_id))
    )
    return {post_id: count for post_id, count in session.exec(statement).all()}


def count_posts(session: Session, blocked_author_ids: set[int] | None = None) -> int:
    """게시글 총 개수 (모임 게시글 제외)"""
    statement = select(func.count()).select_from(Post).where(
        col(Post.group_id).is_(None)
    )
    if blocked_author_ids:
        statement = statement.where(col(Post.author_id).notin_(blocked_author_ids))
    return session.exec(statement).one()


def count_group_posts(
    session: Session,
    group_id: int,
    blocked_author_ids: set[int] | None = None,
) -> int:
    """모임 게시글 총 개수. 목록과 같은 기준이라 공지는 빼고 센다."""
    statement = (
        select(func.count())
        .select_from(Post)
        .where(col(Post.group_id) == group_id)
        .where(col(Post.is_notice).is_(False))
    )
    if blocked_author_ids:
        statement = statement.where(col(Post.author_id).notin_(blocked_author_ids))
    return session.exec(statement).one()


def _search_statement(query: str, search_by: PostSearchField, blocked_author_ids: set[int] | None = None):
    # 일반 게시글 검색이므로 모임 게시글은 제외한다(get_posts와 같은 조건).
    statement = select(Post).distinct().where(col(Post.group_id).is_(None))

    if search_by == PostSearchField.TITLE:
        statement = statement.where(col(Post.title).ilike(f"%{query}%"))
    elif search_by == PostSearchField.CONTENT:
        statement = statement.join(
            PostContent,
            (col(PostContent.post_id) == Post.id) & (col(PostContent.type) == "text"),
        ).where(col(PostContent.content).ilike(f"%{query}%"))
    elif search_by == PostSearchField.COMMENT:
        statement = statement.join(Comment, col(Comment.post_id) == Post.id).where(
            col(Comment.content).ilike(f"%{query}%")
        )
    elif search_by == PostSearchField.AUTHOR:
        statement = statement.join(User, col(User.id) == Post.author_id).where(
            col(User.nickname).ilike(f"%{query}%")
        )

    if blocked_author_ids:
        statement = statement.where(col(Post.author_id).notin_(blocked_author_ids))

    return statement


def search_posts(
    session: Session,
    query: str,
    search_by: PostSearchField,
    skip: int = 0,
    limit: int = 10,
    blocked_author_ids: set[int] | None = None,
) -> list[Post]:
    """게시글 검색"""
    statement = _search_statement(query, search_by, blocked_author_ids)
    return list(
        session.exec(
            statement.order_by(col(Post.created_at).desc()).offset(skip).limit(limit)
        ).all()
    )


def count_search_posts(
    session: Session,
    query: str,
    search_by: PostSearchField,
    blocked_author_ids: set[int] | None = None,
) -> int:
    """검색 결과 총 개수.

    목록과 같은 조건을 쓰려고 _search_statement를 그대로 감싼다. 그 문장은
    JOIN과 DISTINCT를 쓰므로, COUNT를 바로 붙이면 JOIN으로 늘어난 행까지
    세어 목록보다 큰 숫자가 나온다. 서브쿼리의 행을 세면 목록과 일치한다.
    """
    subquery = _search_statement(query, search_by, blocked_author_ids).subquery()
    return session.exec(select(func.count()).select_from(subquery)).one()


def set_group_notice(session: Session, post: Post, is_notice: bool) -> Post:
    """모임 공지를 지정하거나 해제한다.

    모임당 하나만 둔다. 화면이 배너에 한 건만 띄우는데 여러 개를 허용하면
    나머지 공지가 목록에서도 배너에서도 빠져 아무 데도 안 보인다.
    """
    if is_notice and post.group_id is not None:
        for other in session.exec(
            select(Post)
            .where(col(Post.group_id) == post.group_id)
            .where(col(Post.is_notice).is_(True))
            .where(col(Post.id) != post.id)
        ).all():
            other.is_notice = False
            session.add(other)

    post.is_notice = is_notice
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def get_group_notice(session: Session, group_id: int) -> Post | None:
    """모임의 공지 글. 없으면 None.

    모임당 하나만 켤 수 있으므로 첫 건을 그대로 쓴다.
    """
    return session.exec(
        select(Post)
        .where(col(Post.group_id) == group_id)
        .where(col(Post.is_notice).is_(True))
    ).first()
