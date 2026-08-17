from datetime import date, datetime, timedelta, timezone

from pydantic import EmailStr
from sqlalchemy import delete, func
from sqlmodel import Session, col, select

from models import (
    ChatRoomMember,
    FCMToken,
    MessageReadReceipt,
    RefreshToken,
    User,
    UserBlock,
    UserDisease,
)
from models.group import GroupApplication, GroupMember
from models.health import Schedule, StepGoal, StepRecord
from models.user import DELETED_NICKNAME
from schemas import UserCreate, UserUpdate
from security import get_password_hash, verify_password


def create_user(
    session: Session, user_create: UserCreate, profile_pic_url: str | None = None
) -> User:
    """사용자 생성"""
    user_data = user_create.model_dump(exclude={"password", "otp"}, exclude_unset=True)
    hashed_pw = get_password_hash(user_create.password)
    user = User(**user_data, hashed_password=hashed_pw)
    if profile_pic_url:
        user.profile_pic = profile_pic_url

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user(session: Session, id: int) -> User | None:
    """내부 ID로 사용자 조회"""
    return session.get(User, id)


def get_user_by_login_id(session: Session, login_id: str) -> User | None:
    """로그인 ID로 사용자 조회 (탈퇴 계정 제외)"""
    statement = select(User).where(
        User.login_id == login_id, col(User.is_deleted).is_(False)
    )
    return session.exec(statement).first()


def get_user_by_email(session: Session, email: EmailStr) -> User | None:
    """이메일로 사용자 조회 (탈퇴 계정 제외)"""
    statement = select(User).where(
        User.email == email, col(User.is_deleted).is_(False)
    )
    return session.exec(statement).first()


def get_id_by_email(session: Session, email: EmailStr) -> str | None:
    """이메일로 로그인 ID 조회"""
    statement = select(User.login_id).where(User.email == email)
    return session.exec(statement).first()


def get_user_by_phone_number(session: Session, phone_number: str) -> User | None:
    """휴대폰 번호로 사용자 조회 (탈퇴 계정 제외).

    탈퇴한 계정은 번호를 놓아주므로 같은 번호로 다시 가입할 수 있다.
    """
    statement = select(User).where(
        User.phone_number == phone_number, col(User.is_deleted).is_(False)
    )
    return session.exec(statement).first()


def get_users(session: Session, skip: int = 0, limit: int = 10) -> list[User]:
    """사용자 목록 조회"""
    statement = select(User).offset(skip).limit(limit)
    return list(session.exec(statement).all())


def update_user(session: Session, user: User, user_update: UserUpdate) -> User:
    """사용자 정보 수정"""
    update_data = user_update.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    for key, value in update_data.items():
        setattr(user, key, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, id: str, password: str) -> User | None:
    """사용자 인증(로그인). 탈퇴한 계정은 조회되지 않아 로그인할 수 없다."""
    if "@" in id:
        user = get_user_by_email(session, id)
    else:
        user = get_user_by_login_id(session, id)
    if not user:
        return None
    if not verify_password(user.hashed_password, password):
        return None
    return user


def suspend_user(session: Session, user: User, days: int) -> User:
    """사용자 계정 정지. days=-1이면 영구 정지"""
    if days == -1:
        user.suspended_until = datetime(9999, 12, 31, tzinfo=timezone.utc)
    else:
        user.suspended_until = datetime.now(timezone.utc) + timedelta(days=days)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_phone_number(session: Session, user: User, phone_number: str) -> User:
    """휴대폰 번호 변경"""
    user.phone_number = phone_number
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_profile_pic(session: Session, user: User, url: str) -> User:
    """프로필 사진 URL 업데이트"""
    user.profile_pic = url
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def block_user(session: Session, blocker_id: int, blocked_id: int) -> None:
    """사용자 차단"""
    if not session.get(UserBlock, (blocker_id, blocked_id)):
        session.add(UserBlock(blocker_id=blocker_id, blocked_id=blocked_id))
        session.commit()


def unblock_user(session: Session, blocker_id: int, blocked_id: int) -> None:
    """사용자 차단 해제"""
    block = session.get(UserBlock, (blocker_id, blocked_id))
    if block:
        session.delete(block)
        session.commit()


def get_blocked_user_ids(session: Session, user_id: int) -> set[int]:
    """차단한 유저 ID 목록"""
    statement = select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id)
    return set(session.exec(statement).all())


def get_block_times(session: Session, blocker_id: int) -> dict[int, datetime]:
    """내가 차단한 사람 -> 차단한 시각.

    채팅에서 이 시각 이후에 그 사람이 보낸 쪽지만 가린다. 차단 전에 나눈
    대화까지 사라지면 이용자가 당황하므로 경계를 시각으로 잡는다.
    """
    rows = session.exec(
        select(UserBlock).where(col(UserBlock.blocker_id) == blocker_id)
    ).all()
    return {row.blocked_id: row.created_at for row in rows}


def get_blockers_among(
    session: Session, blocked_id: int, candidates: list[int]
) -> set[int]:
    """[candidates] 중 [blocked_id]를 차단해 둔 사람들.

    보낸 사람에게는 아무 표시도 하지 않는 조용한 차단이라, 전달 대상에서만
    조용히 빼기 위해 쓴다.
    """
    if not candidates:
        return set()
    rows = session.exec(
        select(UserBlock.blocker_id)
        .where(col(UserBlock.blocked_id) == blocked_id)
        .where(col(UserBlock.blocker_id).in_(candidates))
    ).all()
    return set(rows)


def is_login_id_available(session: Session, login_id: str) -> bool:
    return get_user_by_login_id(session, login_id) is None


def is_phone_number_available(session: Session, phone_number: str) -> bool:
    return get_user_by_phone_number(session, phone_number) is None


def is_nickname_available(session: Session, nickname: str) -> bool:
    return not session.exec(
        select(User.id).where(
            User.nickname == nickname, col(User.is_deleted).is_(False)
        )
    ).first()


def get_user_by_nickname(session: Session, nickname: str) -> User | None:
    """닉네임으로 사용자 조회 (차단 기능에서 사용)"""
    statement = select(User).where(
        User.nickname == nickname, col(User.is_deleted).is_(False)
    )
    return session.exec(statement).first()


def get_blocked_users(session: Session, user_id: int) -> list[User]:
    """내가 차단한 사용자 목록"""
    statement = (
        select(User)
        .join(UserBlock, col(UserBlock.blocked_id) == User.id)
        .where(UserBlock.blocker_id == user_id)
    )
    return list(session.exec(statement).all())


def anonymize_user(session: Session, user: User) -> None:
    """회원 탈퇴 시 계정에서 개인정보를 지운다.

    행 자체는 남긴다. post.author_id 등이 참조하고 있어 지우면 게시글까지
    사라지기 때문이다. 대신 식별에 쓰일 수 있는 값을 모두 덮어써서 남은 행이
    "누구였는지 알 수 없는 껍데기"가 되게 한다.

    부분 유니크 인덱스(WHERE is_deleted = false) 덕분에 탈퇴 계정끼리는 같은
    값을 가져도 되고, 원래 쓰던 아이디/번호/닉네임은 다른 사람이 다시 쓸 수 있다.
    """
    user.is_deleted = True
    user.login_id = "deleted_id"
    user.phone_number = "01000000000"
    user.email = None
    user.nickname = DELETED_NICKNAME
    user.date_of_birth = date(1900, 1, 1)
    # 해시 형식이 아닌 값이라 어떤 비밀번호로도 검증에 성공할 수 없다.
    user.hashed_password = "!deleted"
    user.profile_pic = None
    # gender는 다른 식별 정보가 모두 지워진 뒤라 단독으로 개인을 특정할 수
    # 없어 그대로 둔다.
    session.add(user)
    session.commit()


def delete_user_personal_data(session: Session, user_id: int) -> None:
    """탈퇴 시 함께 지워야 하는 연관 데이터.

    - 건강 정보(일정/걸음수)는 민감정보라 보관할 이유가 없다
    - FCM 토큰이 남으면 탈퇴한 사용자 기기로 푸시가 계속 간다
    - 리프레시 토큰이 남으면 탈퇴 후에도 새 액세스 토큰을 받아갈 수 있다
    - 모임/채팅 참여와 차단 관계는 유지되면 동작이 어색해진다

    게시글·댓글과 그에 달린 좋아요·신고 기록은 남긴다(대화 맥락 보존).
    """
    for statement in (
        delete(RefreshToken).where(col(RefreshToken.user_id) == user_id),
        delete(UserDisease).where(col(UserDisease.user_id) == user_id),
        delete(Schedule).where(col(Schedule.user_id) == user_id),
        delete(StepGoal).where(col(StepGoal.user_id) == user_id),
        delete(StepRecord).where(col(StepRecord.user_id) == user_id),
        delete(FCMToken).where(col(FCMToken.user_id) == user_id),
        delete(GroupMember).where(col(GroupMember.user_id) == user_id),
        delete(GroupApplication).where(col(GroupApplication.user_id) == user_id),
        delete(ChatRoomMember).where(col(ChatRoomMember.user_id) == user_id),
        delete(MessageReadReceipt).where(col(MessageReadReceipt.user_id) == user_id),
        # 차단은 양방향 모두 정리한다.
        delete(UserBlock).where(col(UserBlock.blocker_id) == user_id),
        delete(UserBlock).where(col(UserBlock.blocked_id) == user_id),
    ):
        session.exec(statement)
    session.commit()


# 사용자 삭제(탈퇴)도 있어야


def count_suspended_users(session: Session) -> int:
    """지금 정지 중인 계정 수.

    기간이 지난 정지는 세지 않는다. suspended_until만 보고 세면 예전에
    한 번 정지된 적 있는 사람까지 계속 잡힌다.
    """
    now = datetime.now(timezone.utc)
    statement = (
        select(func.count())
        .select_from(User)
        .where(col(User.is_deleted).is_(False))
        .where(col(User.suspended_until) > now)
    )
    return session.exec(statement).one()
