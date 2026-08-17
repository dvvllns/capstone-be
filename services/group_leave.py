from sqlmodel import Session

from crud import group as group_crud
from crud import upload as upload_crud
from utils.image import delete_image


def hand_over_or_delete(session: Session, group, user_id: int) -> None:
    """모임장이 나갈 때 모임을 어떻게 할지 정한다.

    가장 먼저 가입한 다른 멤버에게 모임장을 넘긴다. 넘길 사람이 아무도 없으면
    아무도 관리할 수 없는 모임이 남으므로 모임을 삭제한다.

    회원 탈퇴와 모임 탈퇴 양쪽에서 같은 규칙을 써야 해서 여기로 모았다.
    """
    assert group.id is not None
    new_leader_id = group_crud.get_oldest_member_id(session, group.id, user_id)
    if new_leader_id is not None:
        group_crud.transfer_leadership(session, group, new_leader_id)
        return

    cover_image = group.cover_image
    group_crud.delete_group(session, group)
    if cover_image:
        delete_image(cover_image)
        upload_crud.delete_log_by_url(session, cover_image)
