from sqlalchemy import delete, func
from sqlmodel import Session, col, select

from models.group import Group, GroupApplication, GroupMember
from schemas.group import (
    ApplicationStatus,
    GroupCreate,
    GroupSearchField,
    GroupUpdate,
)


def create_group(session: Session, creator_id: int, group_create: GroupCreate) -> Group:
    group = Group(
        name=group_create.name,
        description=group_create.description,
        leader_id=creator_id,
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    assert group.id is not None
    session.add(GroupMember(group_id=group.id, user_id=creator_id))
    session.commit()
    return group


def get_group(session: Session, group_id: int) -> Group | None:
    return session.get(Group, group_id)


def get_groups(session: Session, skip: int = 0, limit: int = 20) -> list[Group]:
    return list(
        session.exec(
            select(Group).order_by(col(Group.created_at).desc()).offset(skip).limit(limit)
        ).all()
    )


def count_groups(session: Session) -> int:
    return session.exec(select(func.count()).select_from(Group)).one()


def update_group(session: Session, group: Group, group_update: GroupUpdate) -> Group:
    for key, value in group_update.model_dump(exclude_unset=True).items():
        setattr(group, key, value)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def update_cover_image(session: Session, group: Group, url: str) -> Group:
    group.cover_image = url
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def delete_group(session: Session, group: Group) -> None:
    session.delete(group)
    session.commit()


def is_member(session: Session, user_id: int, group_id: int) -> bool:
    return session.get(GroupMember, (group_id, user_id)) is not None


def get_members(session: Session, group_id: int) -> list[GroupMember]:
    return list(
        session.exec(
            select(GroupMember)
            .where(col(GroupMember.group_id) == group_id)
            .order_by(col(GroupMember.joined_at).asc())
        ).all()
    )


def apply_to_group(session: Session, user_id: int, group_id: int) -> GroupApplication | None:
    """이미 멤버이거나 대기 중인 신청이 있으면 None 반환"""
    if is_member(session, user_id, group_id):
        return None
    existing = session.exec(
        select(GroupApplication)
        .where(col(GroupApplication.user_id) == user_id)
        .where(col(GroupApplication.group_id) == group_id)
        .where(col(GroupApplication.status) == ApplicationStatus.PENDING)
    ).first()
    if existing:
        return None
    application = GroupApplication(user_id=user_id, group_id=group_id)
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def get_applications_by_user(session: Session, user_id: int) -> list[GroupApplication]:
    """사용자가 신청한 모든 가입 신청 목록"""
    return list(
        session.exec(
            select(GroupApplication)
            .where(col(GroupApplication.user_id) == user_id)
            .order_by(col(GroupApplication.created_at).desc())
        ).all()
    )


def get_pending_applications(session: Session, group_id: int) -> list[GroupApplication]:
    return list(
        session.exec(
            select(GroupApplication)
            .where(col(GroupApplication.group_id) == group_id)
            .where(col(GroupApplication.status) == ApplicationStatus.PENDING)
            .order_by(col(GroupApplication.created_at).asc())
        ).all()
    )


def get_application(session: Session, application_id: int) -> GroupApplication | None:
    return session.get(GroupApplication, application_id)


def approve_application(session: Session, application: GroupApplication) -> None:
    application.status = ApplicationStatus.APPROVED
    if not is_member(session, application.user_id, application.group_id):
        session.add(GroupMember(group_id=application.group_id, user_id=application.user_id))
    session.add(application)
    session.commit()


def reject_application(session: Session, application: GroupApplication) -> None:
    application.status = ApplicationStatus.REJECTED
    session.add(application)
    session.commit()


def get_my_groups(
    session: Session, user_id: int, skip: int = 0, limit: int = 20
) -> list[Group]:
    """내가 가입한 모임 목록. 모임장도 생성 시 멤버로 등록되므로 함께 나온다."""
    statement = (
        select(Group)
        .join(GroupMember, col(GroupMember.group_id) == Group.id)
        .where(GroupMember.user_id == user_id)
        .order_by(col(GroupMember.joined_at).desc())
        .offset(skip)
        .limit(limit)
    )
    return list(session.exec(statement).all())


def count_my_groups(session: Session, user_id: int) -> int:
    statement = select(func.count()).select_from(GroupMember).where(
        GroupMember.user_id == user_id
    )
    return session.exec(statement).one()


def _search_statement(query: str, search_by: GroupSearchField):
    statement = select(Group)
    if search_by == GroupSearchField.NAME:
        return statement.where(col(Group.name).ilike(f"%{query}%"))
    return statement.where(col(Group.description).ilike(f"%{query}%"))


def search_groups(
    session: Session,
    query: str,
    search_by: GroupSearchField,
    skip: int = 0,
    limit: int = 20,
) -> list[Group]:
    """모임 검색 (게시글 검색과 같은 방식)"""
    statement = _search_statement(query, search_by)
    return list(
        session.exec(
            statement.order_by(col(Group.created_at).desc()).offset(skip).limit(limit)
        ).all()
    )


def count_search_groups(
    session: Session, query: str, search_by: GroupSearchField
) -> int:
    # 목록과 조건을 하나로 두려고 같은 문장을 감싼다.
    subquery = _search_statement(query, search_by).subquery()
    return session.exec(select(func.count()).select_from(subquery)).one()


def get_member_count_map(session: Session, group_ids: list[int]) -> dict[int, int]:
    """모임 id -> 멤버 수. 목록에서 모임마다 세지 않도록 한 번에 집계한다."""
    if not group_ids:
        return {}
    statement = (
        select(GroupMember.group_id, func.count())
        .where(col(GroupMember.group_id).in_(group_ids))
        .group_by(col(GroupMember.group_id))
    )
    return {group_id: count for group_id, count in session.exec(statement).all()}


def get_joined_group_ids(
    session: Session, user_id: int, group_ids: list[int]
) -> set[int]:
    """주어진 모임들 중 내가 가입한 것. 가입/입장 버튼을 가르는 데 쓴다."""
    if not group_ids:
        return set()
    statement = (
        select(GroupMember.group_id)
        .where(GroupMember.user_id == user_id)
        .where(col(GroupMember.group_id).in_(group_ids))
    )
    return set(session.exec(statement).all())


def remove_member(session: Session, group_id: int, user_id: int) -> bool:
    """모임에서 멤버를 내보낸다. 멤버가 아니었으면 False.

    대기 중인 가입 신청도 함께 정리해, 강퇴된 사람이 예전 신청으로 다시
    승인되는 일이 없게 한다.
    """
    member = session.get(GroupMember, (group_id, user_id))
    if not member:
        return False

    session.delete(member)
    session.exec(
        delete(GroupApplication)
        .where(col(GroupApplication.group_id) == group_id)
        .where(col(GroupApplication.user_id) == user_id)
        .where(col(GroupApplication.status) == ApplicationStatus.PENDING)
    )
    session.commit()
    return True


def get_groups_led_by(session: Session, user_id: int) -> list[Group]:
    """해당 사용자가 모임장인 모임들"""
    return list(session.exec(select(Group).where(Group.leader_id == user_id)).all())


def get_oldest_member_id(
    session: Session, group_id: int, exclude_user_id: int
) -> int | None:
    """모임에 가장 먼저 가입한 멤버(본인 제외). 없으면 None"""
    statement = (
        select(GroupMember.user_id)
        .where(GroupMember.group_id == group_id)
        .where(col(GroupMember.user_id) != exclude_user_id)
        .order_by(col(GroupMember.joined_at).asc())
        .limit(1)
    )
    return session.exec(statement).first()


def transfer_leadership(session: Session, group: Group, new_leader_id: int) -> Group:
    group.leader_id = new_leader_id
    session.add(group)
    session.commit()
    session.refresh(group)
    return group
