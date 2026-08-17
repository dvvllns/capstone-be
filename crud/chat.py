from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, not_
from sqlmodel import Session, col, select

from models.chat import (
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    FCMToken,
    MessageReadReceipt,
)
from models.user import User


def get_room(session: Session, room_id: int) -> ChatRoom | None:
    return session.get(ChatRoom, room_id)


def find_room(session: Session, group_id: int | None, user_ids: list[int]) -> ChatRoom | None:
    """두 사용자가 이미 공유 중인 채팅방 조회"""
    # 각 user_id가 멤버인 room_id 목록을 구하고, 교집합을 찾음
    subqueries = [
        set(
            session.exec(
                select(ChatRoomMember.room_id).where(col(ChatRoomMember.user_id) == uid)
            ).all()
        )
        for uid in user_ids
    ]
    common_room_ids = subqueries[0].intersection(*subqueries[1:])

    for room_id in common_room_ids:
        room = session.get(ChatRoom, room_id)
        if room and room.group_id == group_id:
            # 해당 방의 멤버 수가 정확히 user_ids 수와 일치하는지 확인 (초과 멤버 없음)
            member_count = session.exec(
                select(func.count())
                .select_from(ChatRoomMember)
                .where(col(ChatRoomMember.room_id) == room_id)
            ).one()
            if member_count == len(user_ids):
                return room
    return None


def create_room(
    session: Session, group_id: int | None, user_ids: list[int]
) -> ChatRoom:
    room = ChatRoom(group_id=group_id)
    session.add(room)
    session.commit()
    session.refresh(room)
    assert room.id is not None
    for uid in user_ids:
        session.add(ChatRoomMember(room_id=room.id, user_id=uid))
    session.commit()
    return room


def is_room_member(session: Session, room_id: int, user_id: int) -> bool:
    return (
        session.get(ChatRoomMember, (room_id, user_id)) is not None
    )


def leave_room(session: Session, room_id: int, user_id: int) -> bool:
    """방에서 나간다. 마지막 사람이 나가면 방과 메시지까지 지운다.

    남은 사람이 있으면 방을 남겨둔다. 그 사람에게는 지난 대화가 그대로
    보여야 하기 때문이다. 반환값은 방이 삭제됐는지 여부.
    """
    member = session.get(ChatRoomMember, (room_id, user_id))
    if member is None:
        return False
    session.delete(member)
    session.commit()

    remaining = session.exec(
        select(ChatRoomMember).where(col(ChatRoomMember.room_id) == room_id)
    ).all()
    if remaining:
        return False

    room = session.get(ChatRoom, room_id)
    if room:
        # 메시지와 읽음 기록은 FK의 ondelete=CASCADE로 함께 지워진다.
        session.delete(room)
        session.commit()
    return True


def get_user_rooms(session: Session, user_id: int) -> list[ChatRoom]:
    room_ids = session.exec(
        select(ChatRoomMember.room_id).where(col(ChatRoomMember.user_id) == user_id)
    ).all()
    if not room_ids:
        return []
    return list(
        session.exec(
            select(ChatRoom)
            .where(col(ChatRoom.id).in_(room_ids))
            .order_by(col(ChatRoom.created_at).desc())
        ).all()
    )


def get_room_members(session: Session, room_id: int) -> list[ChatRoomMember]:
    return list(
        session.exec(
            select(ChatRoomMember).where(col(ChatRoomMember.room_id) == room_id)
        ).all()
    )


def save_message(
    session: Session,
    room_id: int,
    sender_id: int,
    sender_nickname: str,
    content: str = "",
    image_url: str | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        room_id=room_id,
        sender_id=sender_id,
        sender_nickname=sender_nickname,
        content=content,
        image_url=image_url,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


def _hide_blocked(statement, block_times: dict[int, datetime] | None):
    """차단한 뒤에 그 사람이 보낸 메시지를 제외한다.

    차단 전에 나눈 대화는 그대로 남긴다. 조용한 차단이라 보낸 쪽에서는
    평소와 똑같이 보이고, 차단한 쪽에서만 보이지 않는다.
    """
    if not block_times:
        return statement
    for sender_id, blocked_at in block_times.items():
        statement = statement.where(
            not_(
                and_(
                    col(ChatMessage.sender_id) == sender_id,
                    col(ChatMessage.created_at) >= blocked_at,
                )
            )
        )
    return statement


def get_messages(
    session: Session,
    room_id: int,
    skip: int = 0,
    limit: int = 50,
    block_times: dict[int, datetime] | None = None,
    after_id: int | None = None,
) -> list[ChatMessage]:
    """[after_id]를 주면 그 뒤에 생긴 것만 오래된 순으로 돌려준다.

    기기에 이미 저장해 둔 마지막 메시지 다음부터만 받아오는 용도다. 푸시가
    몇 건 유실돼도 다음 한 번의 조회로 밀린 것을 모두 메울 수 있다.
    """
    statement = _hide_blocked(
        select(ChatMessage).where(col(ChatMessage.room_id) == room_id), block_times
    )
    if after_id is not None:
        return list(
            session.exec(
                statement.where(col(ChatMessage.id) > after_id)
                .order_by(col(ChatMessage.id).asc())
                .limit(limit)
            ).all()
        )
    return list(
        session.exec(
            statement.order_by(col(ChatMessage.created_at).desc())
            .offset(skip)
            .limit(limit)
        ).all()
    )


def count_messages(
    session: Session, room_id: int, block_times: dict[int, datetime] | None = None
) -> int:
    statement = _hide_blocked(
        select(func.count())
        .select_from(ChatMessage)
        .where(col(ChatMessage.room_id) == room_id),
        block_times,
    )
    return session.exec(statement).one()


def mark_messages_read(session: Session, room_id: int, user_id: int) -> list[int]:
    """room의 내가 보내지 않은 안 읽은 메시지를 모두 읽음 처리. 읽음 처리된 message_id 목록 반환"""
    messages = session.exec(
        select(ChatMessage)
        .where(col(ChatMessage.room_id) == room_id)
        .where(col(ChatMessage.sender_id) != user_id)
    ).all()

    marked_ids: list[int] = []
    for msg in messages:
        assert msg.id is not None
        existing = session.get(MessageReadReceipt, (msg.id, user_id))
        if not existing:
            session.add(MessageReadReceipt(message_id=msg.id, user_id=user_id))
            marked_ids.append(msg.id)
    if marked_ids:
        session.commit()
    return marked_ids


def get_unread_count(
    session: Session,
    room_id: int,
    user_id: int,
    block_times: dict[int, datetime] | None = None,
) -> int:
    """내가 읽지 않은 메시지 수. 차단한 사람이 보낸 것은 세지 않는다."""
    statement = _hide_blocked(
        select(ChatMessage)
        .where(col(ChatMessage.room_id) == room_id)
        .where(col(ChatMessage.sender_id) != user_id),
        block_times,
    )
    messages = session.exec(statement).all()
    count = 0
    for msg in messages:
        assert msg.id is not None
        if not session.get(MessageReadReceipt, (msg.id, user_id)):
            count += 1
    return count


def is_message_read_by_others(session: Session, message: ChatMessage, room_id: int, sender_id: int) -> bool:
    """발신자 외 1명 이상이 읽었는지 확인 (1:1 기준)"""
    assert message.id is not None
    receipts = session.exec(
        select(MessageReadReceipt).where(col(MessageReadReceipt.message_id) == message.id)
    ).all()
    return any(r.user_id != sender_id for r in receipts)


def get_last_message(
    session: Session, room_id: int, block_times: dict[int, datetime] | None = None
) -> ChatMessage | None:
    """목록 미리보기용. 차단한 사람의 쪽지는 미리보기에도 뜨지 않는다."""
    statement = _hide_blocked(
        select(ChatMessage).where(col(ChatMessage.room_id) == room_id), block_times
    )
    return session.exec(
        statement.order_by(col(ChatMessage.created_at).desc()).limit(1)
    ).first()


def upsert_fcm_token(session: Session, user_id: int, token: str) -> FCMToken:
    # 같은 기기를 다른 계정이 쓰던 흔적을 지운다. 기기 토큰은 계정이 아니라
    # 설치본에 붙으므로, 이전 사용자 행에 남겨두면 그 사람에게 온 알림이
    # 지금 기기를 든 사람에게 뜬다.
    for stale in session.exec(
        select(FCMToken).where(
            col(FCMToken.token) == token,
            col(FCMToken.user_id) != user_id,
        )
    ).all():
        session.delete(stale)

    existing = session.get(FCMToken, user_id)
    if existing:
        existing.token = token
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    new_token = FCMToken(user_id=user_id, token=token)
    session.add(new_token)
    session.commit()
    session.refresh(new_token)
    return new_token


def get_fcm_token(session: Session, user_id: int) -> str | None:
    record = session.get(FCMToken, user_id)
    return record.token if record else None


def delete_fcm_token(session: Session, user_id: int) -> None:
    """로그아웃 시 호출. 기기에 더는 알림을 보내지 않는다."""
    record = session.get(FCMToken, user_id)
    if record:
        session.delete(record)
        session.commit()


MESSAGE_RETENTION_DAYS = 7


def update_ack(session: Session, room_id: int, user_id: int, last_message_id: int) -> None:
    """클라이언트가 SQLite에 저장했음을 확인한 마지막 메시지 ID 기록"""
    member = session.get(ChatRoomMember, (room_id, user_id))
    if not member:
        return
    msg = session.get(ChatMessage, last_message_id)
    if not msg or msg.room_id != room_id:
        return
    member.last_ack_id = last_message_id
    member.last_ack_at = msg.created_at
    session.add(member)
    session.commit()


def check_has_deleted(session: Session, room_id: int, user_id: int) -> bool:
    """클라이언트가 마지막으로 ack한 이후 삭제된 메시지가 있는지 확인"""
    member = session.get(ChatRoomMember, (room_id, user_id))
    if not member or member.last_ack_id is None:
        return False

    # 감지 1: ID 공백 — last_ack_id 다음 메시지가 연속하지 않으면 그 사이가 삭제된 것
    oldest_newer = session.exec(
        select(ChatMessage)
        .where(col(ChatMessage.room_id) == room_id)
        .where(col(ChatMessage.id) > member.last_ack_id)
        .order_by(col(ChatMessage.id).asc())
        .limit(1)
    ).first()
    if oldest_newer is not None and oldest_newer.id > member.last_ack_id + 1:
        return True

    # 감지 2: 시간 기반 — ack 시점이 보존 기간을 넘으면 그 사이 메시지가 삭제됐을 수 있음
    # (ID 공백이 없어도 ack 이후 모든 메시지가 삭제된 경우 커버)
    if member.last_ack_at is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=MESSAGE_RETENTION_DAYS)
        if member.last_ack_at < cutoff:
            return True

    return False
