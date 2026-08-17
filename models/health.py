from datetime import date, datetime, time, timezone
from enum import StrEnum

from sqlalchemy import Date, DateTime, Time
from sqlmodel import AutoString, Field, SQLModel


class ScheduleType(StrEnum):
    MEDICATION = "medication"
    APPOINTMENT = "appointment"


class Schedule(SQLModel, table=True):
    """복약과 약속 일정.

    약 먹는 시각과 병원·모임·외출 약속을 함께 다룬다. 둘 다 "정해진 시각에
    알려줘야 하는 일"이라 구분해 둘 이유가 없다.

    단발 일정과 요일 반복 일정을 한 테이블에 담는다. 반복을 행으로 펼치면
    1년치가 수백 행이 되고 시간을 바꿀 때 전부 고쳐야 하므로, 규칙만 저장하고
    조회 시점에 날짜를 펼친다.
    """

    __tablename__ = "schedule"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    type: ScheduleType = Field(sa_type=AutoString())
    title: str = Field(min_length=1, max_length=100)

    # 하루 중 시각. 단발이든 반복이든 이 시각에 울린다.
    scheduled_time: time = Field(sa_type=Time())

    # 단발 일정이면 그 날짜, 반복 일정이면 None.
    scheduled_date: date | None = Field(default=None, sa_type=Date())

    # 반복 요일. 월=1 ... 일=7 (파이썬 isoweekday와 같음).
    # 예: "1,3,5"는 월·수·금. 단발 일정이면 None.
    repeat_days: str | None = Field(default=None, max_length=13)

    # 반복 일정이 시작되는 날. 이 날짜 이전에는 표시하지 않는다.
    start_date: date | None = Field(default=None, sa_type=Date())

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class ScheduleCompletion(SQLModel, table=True):
    """일정을 실제로 이행한 기록.

    반복 일정은 "오늘 아침약 먹음"이 내일까지 이어지면 안 되므로 완료 여부를
    일정이 아니라 (일정, 날짜)에 붙인다. 행이 있으면 그날 완료한 것이다.
    """

    __tablename__ = "schedule_completion"
    schedule_id: int = Field(
        foreign_key="schedule.id", primary_key=True, ondelete="CASCADE"
    )
    completed_date: date = Field(primary_key=True, sa_type=Date())
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
    )


class StepGoal(SQLModel, table=True):
    __tablename__ = "step_goal"
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    daily_goal: int = Field(ge=1)


class StepRecord(SQLModel, table=True):
    __tablename__ = "step_record"
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    record_date: date = Field(primary_key=True, sa_type=Date())
    steps: int = Field(ge=0)
