from datetime import datetime

from sqlmodel import SQLModel


class ChatRoomCreate(SQLModel):
    group_id: int
    other_user_id: int


class ChatRoomMemberInfo(SQLModel):
    user_id: int
    nickname: str
    joined_at: datetime


class ChatRoomResponse(SQLModel):
    id: int
    group_id: int | None
    created_at: datetime
    members: list[ChatRoomMemberInfo]
    last_message: str | None
    last_message_at: datetime | None
    unread_count: int


class MessageResponse(SQLModel):
    id: int
    room_id: int
    sender_id: int
    sender_nickname: str
    content: str
    image_url: str | None
    created_at: datetime
    is_read: bool


class FCMTokenUpdate(SQLModel):
    token: str


class AckRequest(SQLModel):
    last_message_id: int


class ChatMessagePageResponse(SQLModel):
    items: list[MessageResponse]
    total: int
    page: int
    size: int
    pages: int
    has_deleted: bool
