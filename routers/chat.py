import asyncio
from datetime import datetime, timezone
from math import ceil

import jwt
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jwt import PyJWTError
from sqlmodel import Session

from config import settings
from crud import chat as chat_crud
from crud import group as group_crud
from crud import user as user_crud
from database import engine, get_session
from dependencies import Pagination, get_current_user
from models import User
from schemas import AckRequest, ChatMessagePageResponse, ChatRoomCreate, ChatRoomResponse, FCMTokenUpdate, MessageResponse
from schemas.chat import ChatRoomMemberInfo
from services.fcm import send_chat_notification
from utils.image import process_and_save_image
from ws_manager import manager

router = APIRouter(tags=["chat"])


def _ws_auth(token: str, session: Session) -> User:
    """WebSocket 연결용 JWT 인증. 실패 시 None 대신 예외.

    REST는 get_current_user가 탈퇴·정지 계정을 막지만 WS는 그 경로를 타지 않아
    여기서 같은 검사를 직접 한다.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise ValueError
        user = user_crud.get_user(session, int(user_id_str))
        if not user or user.is_deleted:
            raise ValueError
        if user.suspended_until and user.suspended_until > datetime.now(timezone.utc):
            raise ValueError
        return user
    except (PyJWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증 정보가 유효하지 않습니다")


def _room_member_ids(session: Session, room_id: int) -> list[int]:
    return [m.user_id for m in chat_crud.get_room_members(session, room_id)]


async def _broadcast(
    member_ids: list[int], payload: dict, exclude_user_id: int | None = None
) -> None:
    """방 멤버 중 접속 중인 사람에게 보낸다.

    채팅방을 보고 있지 않아도 보낸다. 연결이 사용자당 하나라서, 목록 화면에
    있어도 안 읽은 수를 바로 갱신할 수 있다.
    """
    for uid in member_ids:
        if exclude_user_id is not None and uid == exclude_user_id:
            continue
        await manager.send_to_user(uid, payload)


def _deliverable_ids(
    session: Session, member_ids: list[int], sender_id: int
) -> list[int]:
    """보낸 사람을 차단해 둔 멤버를 뺀 전달 대상.

    차단은 조용히 동작한다. 보낸 쪽에는 거절도 오류도 없고 자기 메시지가
    그대로 되돌아오므로, 상대가 자신을 차단했는지 알 수 없다.
    """
    blockers = user_crud.get_blockers_among(session, sender_id, member_ids)
    if not blockers:
        return member_ids
    return [uid for uid in member_ids if uid not in blockers]


def _collect_push_targets(
    session: Session, member_ids: list[int], sender_id: int, room_id: int
) -> list[tuple[str, bool]]:
    """푸시를 보낼 (토큰, 내용표시여부) 목록.

    그 방을 보고 있는 사람은 소켓으로 이미 받으므로 제외한다.
    세션을 닫은 뒤에는 조회할 수 없어 미리 모아둔다.
    """
    targets: list[tuple[str, bool]] = []
    for uid in member_ids:
        if uid == sender_id or manager.is_viewing(uid, room_id):
            continue
        token = chat_crud.get_fcm_token(session, uid)
        if not token:
            continue
        recipient = user_crud.get_user(session, uid)
        targets.append((token, recipient.notify_message if recipient else True))
    return targets


async def _dispatch_message(
    member_ids: list[int],
    payload: dict,
    push_targets: list[tuple[str, bool]],
    sender_nickname: str,
    preview: str,
    room_id: int,
) -> None:
    # 접속 중인 멤버에게는 방을 보고 있지 않아도 보낸다(목록 화면 갱신용).
    await _broadcast(member_ids, payload)

    # FCM 전송은 네트워크 호출이라 이벤트 루프를 막지 않도록 스레드로 넘긴다.
    for token, show_content in push_targets:
        await asyncio.to_thread(
            send_chat_notification,
            fcm_token=token,
            sender_nickname=sender_nickname,
            content=preview,
            room_id=room_id,
            show_content=show_content,
        )


IMAGE_PREVIEW_TEXT = "사진을 보냈습니다"


def _preview_text(msg) -> str:
    """목록과 푸시에 쓸 한 줄 요약. 사진만 보낸 메시지는 content가 비어 있다."""
    return msg.content if msg.content else IMAGE_PREVIEW_TEXT


def _ws_message_payload(msg) -> dict:
    """소켓으로 내보낼 새 메시지. REST의 MessageResponse와 필드를 맞춘다."""
    return {
        "type": "message",
        "id": msg.id,
        "room_id": msg.room_id,
        "sender_id": msg.sender_id,
        "sender_nickname": msg.sender_nickname,
        "content": msg.content,
        "image_url": msg.image_url,
        "created_at": msg.created_at.isoformat(),
        "is_read": False,
    }


def _build_room_response(session: Session, room, current_user_id: int) -> dict:
    # 차단한 사람의 쪽지는 미리보기에도 안 읽은 개수에도 넣지 않는다.
    block_times = user_crud.get_block_times(session, current_user_id)
    members_db = chat_crud.get_room_members(session, room.id)
    member_infos = []
    for m in members_db:
        u = user_crud.get_user(session, m.user_id)
        if u:
            member_infos.append(
                ChatRoomMemberInfo(user_id=m.user_id, nickname=u.nickname, joined_at=m.joined_at)
            )
    last_msg = chat_crud.get_last_message(session, room.id, block_times)
    unread = chat_crud.get_unread_count(session, room.id, current_user_id, block_times)
    return {
        "id": room.id,
        "group_id": room.group_id,
        "created_at": room.created_at,
        "members": member_infos,
        "last_message": _preview_text(last_msg) if last_msg else None,
        "last_message_at": last_msg.created_at if last_msg else None,
        "unread_count": unread,
    }


def _build_message_response(session: Session, msg, sender_id: int) -> dict:
    is_read = chat_crud.is_message_read_by_others(session, msg, msg.room_id, sender_id)
    return {
        "id": msg.id,
        "room_id": msg.room_id,
        "sender_id": msg.sender_id,
        "sender_nickname": msg.sender_nickname,
        "content": msg.content,
        "image_url": msg.image_url,
        "created_at": msg.created_at,
        "is_read": is_read,
    }


@router.post("/chat/rooms", response_model=ChatRoomResponse, status_code=status.HTTP_201_CREATED)
def create_chat_room(
    body: ChatRoomCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """1:1 채팅방 개설. 같은 그룹 내 모임장-멤버 간만 가능."""
    group = group_crud.get_group(session, body.group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="모임을 찾을 수 없습니다")

    assert current_user.id is not None
    other = user_crud.get_user(session, body.other_user_id)
    if not other:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="상대방을 찾을 수 없습니다")

    if not group_crud.is_member(session, current_user.id, body.group_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="모임 멤버만 채팅을 시작할 수 있습니다")
    if not group_crud.is_member(session, body.other_user_id, body.group_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="상대방이 해당 모임의 멤버가 아닙니다")

    if current_user.id == body.other_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="자신과는 채팅할 수 없습니다")

    existing = chat_crud.find_room(session, body.group_id, [current_user.id, body.other_user_id])
    if existing:
        return _build_room_response(session, existing, current_user.id)

    room = chat_crud.create_room(session, body.group_id, [current_user.id, body.other_user_id])
    return _build_room_response(session, room, current_user.id)


@router.get("/chat/rooms", response_model=list[ChatRoomResponse])
def list_chat_rooms(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내 채팅방 목록 조회"""
    assert current_user.id is not None
    rooms = chat_crud.get_user_rooms(session, current_user.id)
    return [_build_room_response(session, r, current_user.id) for r in rooms]


@router.get("/chat/rooms/{room_id}/messages", response_model=ChatMessagePageResponse)
def list_messages(
    room_id: int,
    pagination: Pagination = Depends(),
    after_id: int | None = Query(
        default=None,
        description="이 id보다 뒤에 생긴 메시지만 오래된 순으로 받는다. 기기에 저장해 둔 마지막 메시지 이후를 채울 때 쓴다.",
    ),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """채팅방 메시지 내역 조회 (최신순 페이지네이션).

    after_id를 주면 증분 조회로 바뀐다. 푸시를 몇 건 놓쳐도 다음 한 번의
    호출로 밀린 것을 모두 메울 수 있다.

    has_deleted=true이면 클라이언트가 오프라인인 동안 삭제된 메시지가 있음.
    """
    assert current_user.id is not None
    if not chat_crud.is_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="채팅방 멤버가 아닙니다")

    block_times = user_crud.get_block_times(session, current_user.id)
    messages = chat_crud.get_messages(
        session, room_id, pagination.skip, pagination.size, block_times, after_id
    )
    total = chat_crud.count_messages(session, room_id, block_times)
    has_deleted = chat_crud.check_has_deleted(session, room_id, current_user.id)

    return {
        "items": [_build_message_response(session, m, m.sender_id) for m in messages],
        "total": total,
        "page": pagination.page,
        "size": pagination.size,
        "pages": ceil(total / pagination.size) if pagination.size > 0 else 0,
        "has_deleted": has_deleted,
    }


@router.post("/chat/rooms/{room_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    room_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """채팅방의 안 읽은 메시지 전체 읽음 처리 (HTTP 폴백용)"""
    assert current_user.id is not None
    if not chat_crud.is_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="채팅방 멤버가 아닙니다")

    marked_ids = chat_crud.mark_messages_read(session, room_id, current_user.id)
    if marked_ids:
        await _broadcast(
            _room_member_ids(session, room_id),
            {
                "type": "read",
                "room_id": room_id,
                "user_id": current_user.id,
                "message_ids": marked_ids,
            },
            exclude_user_id=current_user.id,
        )


@router.post(
    "/chat/rooms/{room_id}/images",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_image_message(
    room_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """사진 메시지 전송.

    사진은 바이너리라 WebSocket으로 보내기 번거로워 REST로 올린다. 저장한 뒤에는
    글 메시지와 똑같이 소켓 브로드캐스트와 푸시를 태우므로, 받는 쪽은 경로 차이를
    알 필요가 없다.
    """
    assert current_user.id is not None
    if not chat_crud.is_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="채팅방 멤버가 아닙니다")

    image_url, _ = process_and_save_image(file, "chat")

    msg = chat_crud.save_message(
        session, room_id, current_user.id, current_user.nickname, image_url=image_url
    )
    member_ids = _room_member_ids(session, room_id)
    deliver_ids = _deliverable_ids(session, member_ids, current_user.id)
    push_targets = _collect_push_targets(session, deliver_ids, current_user.id, room_id)

    await _dispatch_message(
        deliver_ids,
        _ws_message_payload(msg),
        push_targets,
        current_user.nickname,
        IMAGE_PREVIEW_TEXT,
        room_id,
    )
    return _build_message_response(session, msg, msg.sender_id)


@router.post("/chat/rooms/{room_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_chat_room(
    room_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """쪽지방 나가기.

    남은 사람에게는 지난 대화가 그대로 보인다. 마지막 사람이 나가면 방과 메시지를
    지운다. 나간 뒤 같은 상대와 다시 쪽지를 시작하면 새 방이 열린다.
    """
    assert current_user.id is not None
    if not chat_crud.is_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="채팅방 멤버가 아닙니다")
    chat_crud.leave_room(session, room_id, current_user.id)


@router.post("/chat/rooms/{room_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
def ack_messages(
    room_id: int,
    body: AckRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """클라이언트가 메시지를 SQLite에 저장한 후 호출. 마지막 저장 메시지 ID를 서버에 기록."""
    assert current_user.id is not None
    if not chat_crud.is_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="채팅방 멤버가 아닙니다")
    chat_crud.update_ack(session, room_id, current_user.id, body.last_message_id)


@router.put("/users/me/fcm-token", status_code=status.HTTP_204_NO_CONTENT)
def update_fcm_token(
    body: FCMTokenUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """FCM 디바이스 토큰 등록/갱신"""
    assert current_user.id is not None
    chat_crud.upsert_fcm_token(session, current_user.id, body.token)


@router.delete("/users/me/fcm-token", status_code=status.HTTP_204_NO_CONTENT)
def remove_fcm_token(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """로그아웃 시 호출. 이 계정 앞으로 오던 푸시를 끊는다."""
    assert current_user.id is not None
    chat_crud.delete_fcm_token(session, current_user.id)


async def _handle_enter_room(user: User, data: dict) -> None:
    """채팅방 화면 진입. 여기서부터 그 방 메시지는 푸시 대신 소켓으로 간다."""
    room_id = data.get("room_id")
    if not isinstance(room_id, int):
        await manager.send_to_user(
            user.id, {"type": "error", "detail": "room_id가 필요합니다"}
        )
        return

    with Session(engine) as session:
        if not chat_crud.is_room_member(session, room_id, user.id):
            await manager.send_to_user(
                user.id, {"type": "error", "detail": "채팅방 멤버가 아닙니다"}
            )
            return

        manager.enter_room(user.id, room_id)

        # 화면에 들어왔으니 안 읽은 메시지를 읽음 처리한다.
        marked_ids = chat_crud.mark_messages_read(session, room_id, user.id)
        has_deleted = chat_crud.check_has_deleted(session, room_id, user.id)
        member_ids = _room_member_ids(session, room_id)

    await manager.send_to_user(
        user.id,
        {"type": "entered", "room_id": room_id, "has_deleted": has_deleted},
    )
    if marked_ids:
        await _broadcast(
            member_ids,
            {
                "type": "read",
                "room_id": room_id,
                "user_id": user.id,
                "message_ids": marked_ids,
            },
            exclude_user_id=user.id,
        )


async def _handle_message(user: User, data: dict) -> None:
    room_id = data.get("room_id")
    content: str = (data.get("content") or "").strip()

    if not isinstance(room_id, int):
        await manager.send_to_user(
            user.id, {"type": "error", "detail": "room_id가 필요합니다"}
        )
        return
    if not content or len(content) > 1000:
        await manager.send_to_user(
            user.id, {"type": "error", "detail": "유효하지 않은 메시지입니다"}
        )
        return

    with Session(engine) as session:
        if not chat_crud.is_room_member(session, room_id, user.id):
            await manager.send_to_user(
                user.id, {"type": "error", "detail": "채팅방 멤버가 아닙니다"}
            )
            return

        msg = chat_crud.save_message(
            session, room_id, user.id, user.nickname, content
        )
        member_ids = _room_member_ids(session, room_id)
        deliver_ids = _deliverable_ids(session, member_ids, user.id)
        push_targets = _collect_push_targets(session, deliver_ids, user.id, room_id)
        payload = _ws_message_payload(msg)

    await _dispatch_message(
        deliver_ids, payload, push_targets, user.nickname, content, room_id
    )


async def _handle_read(user: User, data: dict) -> None:
    room_id = data.get("room_id")
    if not isinstance(room_id, int):
        await manager.send_to_user(
            user.id, {"type": "error", "detail": "room_id가 필요합니다"}
        )
        return

    with Session(engine) as session:
        if not chat_crud.is_room_member(session, room_id, user.id):
            return
        marked_ids = chat_crud.mark_messages_read(session, room_id, user.id)
        member_ids = _room_member_ids(session, room_id)

    if marked_ids:
        await _broadcast(
            member_ids,
            {
                "type": "read",
                "room_id": room_id,
                "user_id": user.id,
                "message_ids": marked_ids,
            },
            exclude_user_id=user.id,
        )


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: str = Query(...)):
    """실시간 채팅 WebSocket. 사용자당 하나만 연결한다.

    로그인 후 한 번 열어 앱이 떠 있는 동안 유지하고, 채팅방을 여닫을 때는
    enter_room / leave_room으로 알린다. 서버는 이 값을 보고 그 방을 보고 있는
    사람에게는 소켓으로, 나머지에게는 FCM 푸시로 새 메시지를 전달한다.

    연결 시 token 쿼리 파라미터로 JWT를 전달해야 한다.

    클라이언트 → 서버:
      {"type": "enter_room", "room_id": 1}
      {"type": "leave_room"}
      {"type": "message", "room_id": 1, "content": "..."}
      {"type": "read", "room_id": 1}
      {"type": "ping"}

    서버 → 클라이언트:
      {"type": "entered", "room_id": 1, "has_deleted": false}
      {"type": "message", "id": 1, "room_id": 1, ...}
      {"type": "read", "room_id": 1, "user_id": 2, "message_ids": [...]}
      {"type": "pong"}
      {"type": "error", "detail": "..."}
    """
    with Session(engine) as session:
        try:
            current_user = _ws_auth(token, session)
        except HTTPException:
            await websocket.close(code=4001)
            return

    assert current_user.id is not None
    await manager.connect(current_user.id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "ping":
                # 모바일에서 조용히 끊긴 연결을 감지하기 위한 keepalive.
                await websocket.send_json({"type": "pong"})
            elif event_type == "enter_room":
                await _handle_enter_room(current_user, data)
            elif event_type == "leave_room":
                manager.leave_room(current_user.id)
                await websocket.send_json({"type": "left_room"})
            elif event_type == "message":
                await _handle_message(current_user, data)
            elif event_type == "read":
                await _handle_read(current_user, data)
            else:
                await websocket.send_json(
                    {"type": "error", "detail": "알 수 없는 요청입니다"}
                )

    except WebSocketDisconnect:
        manager.disconnect(current_user.id, websocket)
    except Exception:
        manager.disconnect(current_user.id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
