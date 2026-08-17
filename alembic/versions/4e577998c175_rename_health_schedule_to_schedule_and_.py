"""rename health_schedule to schedule and hospital to appointment

Revision ID: 4e577998c175
Revises: 66dbd411e028
Create Date: 2026-08-17 05:03:23.628588

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import sqlmodel



# revision identifiers, used by Alembic.
revision: str = '4e577998c175'
down_revision: Union[str, Sequence[str], None] = '66dbd411e028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 병원 일정만 다루던 때의 이름이라 쓰임과 맞지 않는다.
    # 이름만 바꾸면 되므로 데이터를 옮길 필요는 없다.
    op.rename_table("health_schedule", "schedule")

    # 병원 외에 사람 만나기·외출도 담게 되어 값 이름을 넓혔다.
    # 기존 행을 그대로 두면 앱이 모르는 값이 되어 화면에서 사라진다.
    op.execute("UPDATE schedule SET type = 'appointment' WHERE type = 'hospital'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE schedule SET type = 'hospital' WHERE type = 'appointment'")
    op.rename_table("schedule", "health_schedule")
