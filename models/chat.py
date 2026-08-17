from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class ChatRoom(SQLModel, table=True):
    __tablename__ = "chat_room"
    id: int | None = Field(default=None, primary_key=True)
    group_id: int | None = Field(default=None, foreign_key="groups.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class ChatRoomMember(SQLModel, table=True):
    __tablename__ = "chat_room_member"
    room_id: int = Field(foreign_key="chat_room.id", primary_key=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
    # 클라이언트가 SQLite에 저장했음을 확인한 마지막 메시지
    last_ack_id: int | None = None
    last_ack_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="chat_room.id", ondelete="CASCADE")
    sender_id: int = Field(foreign_key="user.id")
    sender_nickname: str
    # 사진만 보낸 메시지는 content가 빈 문자열이다. 둘 중 하나는 반드시 채워진다.
    content: str = Field(default="", max_length=1000)
    image_url: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class MessageReadReceipt(SQLModel, table=True):
    __tablename__ = "message_read_receipt"
    message_id: int = Field(foreign_key="chat_message.id", primary_key=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    read_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class FCMToken(SQLModel, table=True):
    __tablename__ = "fcm_token"
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    token: str
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )
