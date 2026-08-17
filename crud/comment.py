from sqlalchemy import func
from sqlmodel import Session, col, select, update

from models import ChatMessage, Comment, CommentLike
from schemas import CommentCreate, CommentUpdate


def create_comment(
    session: Session,
    comment_create: CommentCreate,
    author_id: int,
    post_id: int,
    author_nickname: str | None,
    parent_id: int | None = None,
) -> Comment | None:
    """댓글 작성"""
    if parent_id:
        parent_comment = session.get(Comment, parent_id)
        if parent_comment and parent_comment.parent:
            return None

    comment = Comment(
        content=comment_create.content,
        author_id=author_id,
        post_id=post_id,
        parent_id=parent_id,
        author_nickname=author_nickname,
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


def update_chat_nickname(session: Session, sender_id: int, new_nickname: str) -> None:
    """채팅 메시지에도 보낸 사람 닉네임이 복사돼 있어 함께 갱신한다."""
    session.exec(
        update(ChatMessage)
        .where(col(ChatMessage.sender_id) == sender_id)
        .values(sender_nickname=new_nickname)
    )
    session.commit()


def update_comments_nickname(session: Session, author_id: int, new_nickname: str) -> None:
    """닉네임 변경 시 해당 유저의 모든 댓글 author_nickname 동기화"""
    session.exec(
        update(Comment)
        .where(col(Comment.author_id) == author_id)
        .where(col(Comment.author_nickname).is_not(None))
        .values(author_nickname=new_nickname)
    )
    session.commit()


def get_anon_order(session: Session, post_id: int) -> dict[int, int]:
    """게시글의 익명 댓글 작성자를 첫 댓글 시간 순으로 번호 매김. {author_id: 순번}"""
    statement = (
        select(Comment.author_id)
        .where(col(Comment.post_id) == post_id)
        .where(col(Comment.author_nickname).is_(None))
        .order_by(col(Comment.created_at).asc())
    )
    result: dict[int, int] = {}
    for author_id in session.exec(statement).all():
        if author_id not in result:
            result[author_id] = len(result) + 1
    return result


def get_comments_by_post(
    session: Session, post_id: int, skip: int = 0, limit: int = 40
) -> list[Comment]:
    """게시글의 댓글 목록 조회"""
    statement = (
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(col(Comment.created_at).asc())
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(statement).all())


def get_comments_by_user(
    session: Session, author_id: int, skip: int = 0, limit: int = 40
) -> list[Comment]:
    """사용자의 댓글 목록 조회"""
    statement = (
        select(Comment)
        .where(Comment.author_id == author_id)
        .order_by(col(Comment.created_at).asc())
        .offset(skip)
        .limit(limit)
    )
    return session.exec(statement).all()


def get_comment(session: Session, id: int) -> Comment | None:
    """댓글 조회"""
    return session.get(Comment, id)


def update_comment(
    session: Session, comment: Comment, comment_update: CommentUpdate
) -> Comment:
    """댓글 수정"""
    comment.content = comment_update.content
    comment.is_edited = True
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


def delete_comment(session: Session, comment: Comment) -> None:
    """댓글 삭제"""
    # 대댓글 존재 여부 검사
    if comment.children:
        comment.content = ""
        session.add(comment)
    else:
        session.delete(comment)
    session.commit()


def toggle_like(
    session: Session, comment: Comment, user_id: int
) -> tuple[Comment, bool]:
    """좋아요 토글. (Comment, liked 여부) 반환"""
    assert comment.id is not None
    like = session.get(CommentLike, (comment.id, user_id))
    if like:
        session.delete(like)
        comment.likes -= 1
        liked = False
    else:
        session.add(CommentLike(comment_id=comment.id, user_id=user_id))
        comment.likes += 1
        liked = True
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment, liked


def count_comments_by_post(session: Session, post_id: int) -> int:
    """게시글의 댓글 수"""
    statement = (
        select(func.count()).select_from(Comment).where(Comment.post_id == post_id)
    )
    return session.exec(statement).one()


def count_comments_by_user(session: Session, author_id: int) -> int:
    """사용자의 댓글 수"""
    statement = (
        select(func.count()).select_from(Comment).where(Comment.author_id == author_id)
    )
    return session.exec(statement).one()
