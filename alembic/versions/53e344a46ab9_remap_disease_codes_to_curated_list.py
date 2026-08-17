"""remap disease codes to curated list

Revision ID: 53e344a46ab9
Revises: 04212cfa0536
Create Date: 2026-08-14 20:12:09.739155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import sqlmodel



# revision identifiers, used by Alembic.
revision: str = '53e344a46ab9'
down_revision: Union[str, Sequence[str], None] = '04212cfa0536'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 16개짜리 임시 목록에서 43개 정식 목록으로 옮긴다.
#
# 뭉뚱그려 두었던 항목이 여러 개로 쪼개진 경우, 사용자가 실제로 무엇을
# 앓는지는 알 수 없다. 그래서 그 분류에서 가장 흔한 것으로 옮긴다.
# 틀릴 수 있지만 지우는 것보다는 낫고, 사용자가 화면에서 고쳐 넣을 수 있다.
CODE_MAP: dict[str, str] = {
    # 이름만 바뀐 것
    "arthritis": "osteoarthritis",
    "back_pain": "herniated_disc",
    "kidney_disease": "chronic_kidney_disease",
    "dementia": "dementia_or_mci",
    # 쪼개진 것 → 가장 흔한 쪽으로
    "respiratory": "asthma",
    "heart_disease": "coronary_artery_disease",
    "eye_disease": "cataract",
    "liver_disease": "fatty_liver",
    "thyroid": "hypothyroidism",
    # 그대로 남는 것: hypertension, diabetes, dyslipidemia,
    #                osteoporosis, stroke, gout, cancer
}


def upgrade() -> None:
    conn = op.get_bind()
    for old, new in CODE_MAP.items():
        # 옮길 자리에 이미 같은 코드가 있으면 (user_id, code) 기본키가 겹친다.
        # 그런 행은 옮기지 않고 지운다.
        conn.execute(
            sa.text(
                "DELETE FROM user_disease a WHERE a.code = :old AND EXISTS ("
                " SELECT 1 FROM user_disease b"
                " WHERE b.user_id = a.user_id AND b.code = :new)"
            ),
            {"old": old, "new": new},
        )
        conn.execute(
            sa.text("UPDATE user_disease SET code = :new WHERE code = :old"),
            {"old": old, "new": new},
        )

    # 새 목록에 없는 코드가 남아 있으면 화면에서 표시할 수 없다.
    conn.execute(
        sa.text(
            "DELETE FROM user_disease WHERE code NOT IN :codes"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": _valid_codes()},
    )


def _valid_codes() -> list[str]:
    from models.disease import DiseaseCode

    return [c.value for c in DiseaseCode]


def downgrade() -> None:
    # 쪼개진 항목을 되돌리면 원래 무엇이었는지 알 수 없다. 되돌리지 않는다.
    pass
