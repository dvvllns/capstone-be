"""탈퇴 계정이 식별자를 놓아주도록 부분 유니크 인덱스로 교체

회원 탈퇴는 행을 지우지 않고 is_deleted만 세운다(게시글/댓글 보존).
그런데 unique 제약이 그대로면 탈퇴한 계정이 전화번호·아이디·닉네임을
계속 붙들고 있어 같은 번호로 다시 가입할 수 없다.

그래서 전체 유니크 제약을 걷어내고 "탈퇴하지 않은 행들 사이에서만"
유일하도록 부분 유니크 인덱스를 건다.

Revision ID: a1b2c3d4e5f6
Revises: b67c7e87b489
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b67c7e87b489"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "is_deleted = false"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("user_phone_number_key", "user", type_="unique")
    op.drop_constraint("user_nickname_key", "user", type_="unique")
    op.drop_constraint("user_email_key", "user", type_="unique")
    op.drop_index("ix_user_login_id", table_name="user")

    op.create_index(
        "uq_user_phone_number_active",
        "user",
        ["phone_number"],
        unique=True,
        postgresql_where=_ACTIVE,
    )
    op.create_index(
        "uq_user_nickname_active",
        "user",
        ["nickname"],
        unique=True,
        postgresql_where=_ACTIVE,
    )
    op.create_index(
        "uq_user_email_active",
        "user",
        ["email"],
        unique=True,
        postgresql_where=_ACTIVE,
    )
    # login_id는 조회에도 쓰이므로 탈퇴 여부와 무관한 일반 인덱스를 함께 둔다.
    op.create_index("ix_user_login_id", "user", ["login_id"], unique=False)
    op.create_index(
        "uq_user_login_id_active",
        "user",
        ["login_id"],
        unique=True,
        postgresql_where=_ACTIVE,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_user_login_id_active", table_name="user")
    op.drop_index("ix_user_login_id", table_name="user")
    op.drop_index("uq_user_email_active", table_name="user")
    op.drop_index("uq_user_nickname_active", table_name="user")
    op.drop_index("uq_user_phone_number_active", table_name="user")

    op.create_index("ix_user_login_id", "user", ["login_id"], unique=True)
    op.create_unique_constraint("user_email_key", "user", ["email"])
    op.create_unique_constraint("user_nickname_key", "user", ["nickname"])
    op.create_unique_constraint("user_phone_number_key", "user", ["phone_number"])
