from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class ApplicationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class GroupSearchField(StrEnum):
    NAME = "name"
    DESCRIPTION = "description"


class GroupCreate(SQLModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)


class GroupUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, min_length=1, max_length=500)

    model_config = ConfigDict(str_strip_whitespace=True)


class NoticePostSummary(SQLModel):
    """모임 화면 맨 위 배너에 쓸 공지 글.

    제목만 보여주므로 본문 블록은 싣지 않는다. 블록까지 넣으면 배너가 쓰지도
    않는 값을 위해 쿼리가 하나 더 나간다.
    """

    id: int
    title: str


class GroupResponse(SQLModel):
    id: int
    name: str
    description: str
    cover_image: str | None
    leader_id: int
    created_at: datetime
    # 목록 카드와 가입/입장 버튼 분기에 필요한 값.
    # is_member는 서버만 알 수 있어(groupmember 조회) 함께 내려준다.
    member_count: int = 0
    is_member: bool = False
    # 공지로 지정된 글. 없거나 비멤버면 null이다.
    #
    # 글 목록이 아니라 여기에 싣는 이유는, 목록에 섞어 보내면 공지가 첫
    # 페이지 한 칸을 먹어 페이지마다 글 개수가 달라지기 때문이다.
    notice_post: NoticePostSummary | None = None


class GroupListResponse(SQLModel):
    id: int
    name: str
    description: str
    cover_image: str | None
    leader_id: int
    created_at: datetime
    member_count: int = 0
    is_member: bool = False


class GroupMemberResponse(SQLModel):
    user_id: int
    joined_at: datetime
    # 앱은 멤버를 이름으로 보여주므로 닉네임이 필요하다.
    nickname: str
    profile_pic: str | None = None
    is_leader: bool = False


class ApplicationResponse(SQLModel):
    id: int
    group_id: int
    user_id: int
    status: ApplicationStatus
    created_at: datetime
    # 모임장이 "누가 신청했는지" 볼 수 있어야 한다.
    nickname: str | None = None
    profile_pic: str | None = None


class TransferLeaderRequest(SQLModel):
    new_leader_id: int
