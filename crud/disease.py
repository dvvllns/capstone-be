from sqlalchemy import delete
from sqlmodel import Session, col, select

from models.disease import DiseaseCode, UserDisease


def get_user_diseases(session: Session, user_id: int) -> list[DiseaseCode]:
    rows = session.exec(
        select(UserDisease).where(col(UserDisease.user_id) == user_id)
    ).all()
    return [row.code for row in rows]


def set_user_diseases(
    session: Session, user_id: int, codes: list[DiseaseCode]
) -> list[DiseaseCode]:
    """선택한 질환 목록을 통째로 교체한다.

    항목별로 추가/삭제를 받는 대신 전체를 받는다. 화면이 체크박스 묶음이라
    "지금 선택된 것"을 그대로 보내는 편이 앱과 서버의 상태가 어긋날 여지가 적다.
    """
    session.exec(delete(UserDisease).where(col(UserDisease.user_id) == user_id))
    unique = list(dict.fromkeys(codes))
    for code in unique:
        session.add(UserDisease(user_id=user_id, code=code))
    session.commit()
    return unique
