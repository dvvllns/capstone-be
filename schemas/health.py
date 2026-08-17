import re
from datetime import date, datetime, time

from pydantic import field_validator, model_validator
from sqlmodel import Field, SQLModel

from models.health import ScheduleType

_REPEAT_DAYS_PATTERN = re.compile(r"[1-7](,[1-7])*")


def _validate_repeat_days(v: str | None) -> str | None:
    """월=1 ... 일=7을 쉼표로 이은 문자열. 예: "1,3,5"는 월·수·금."""
    if v is None:
        return v
    if not _REPEAT_DAYS_PATTERN.fullmatch(v):
        raise ValueError("반복 요일은 1~7 사이 숫자를 쉼표로 이어 적어야 합니다")

    days = v.split(",")
    if len(set(days)) != len(days):
        raise ValueError("반복 요일이 중복되었습니다")
    # 화면에서 요일 순서를 신경 쓰지 않아도 되게 정렬해 저장한다.
    return ",".join(sorted(days))


class ScheduleCreate(SQLModel):
    """일정 생성.

    scheduled_date를 주면 그 날 한 번, repeat_days를 주면 매주 그 요일마다
    울린다. 둘 중 하나만 지정해야 한다.
    """

    type: ScheduleType
    title: str = Field(min_length=1, max_length=100)
    scheduled_time: time
    scheduled_date: date | None = None
    repeat_days: str | None = Field(default=None, max_length=13)
    start_date: date | None = None

    @field_validator("repeat_days")
    @classmethod
    def repeat_days_check(cls, v: str | None) -> str | None:
        return _validate_repeat_days(v)

    @model_validator(mode="after")
    def check_schedule_kind(self) -> "ScheduleCreate":
        if (self.scheduled_date is None) == (self.repeat_days is None):
            raise ValueError(
                "날짜(scheduled_date)나 반복 요일(repeat_days) 중 하나만 지정해야 합니다"
            )
        return self


class ScheduleUpdate(SQLModel):
    type: ScheduleType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=100)
    scheduled_time: time | None = None
    scheduled_date: date | None = None
    repeat_days: str | None = Field(default=None, max_length=13)
    start_date: date | None = None

    @field_validator("repeat_days")
    @classmethod
    def repeat_days_check(cls, v: str | None) -> str | None:
        return _validate_repeat_days(v)


class ScheduleBulkDelete(SQLModel):
    """일괄 삭제 요청.

    id만 받는다. 제목과 시각은 서버가 그 id로 찾아 쓴다.
    """

    ids: list[int] = Field(min_length=1)


class ScheduleBulkDeleteResult(SQLModel):
    # 고른 개수가 아니라 실제로 지워진 개수. 같은 제목·시각인 일정이 함께
    # 지워지므로 고른 것보다 많을 수 있다.
    deleted: int


class ScheduleResponse(SQLModel):
    """저장된 일정 규칙 자체."""

    id: int
    user_id: int
    type: ScheduleType
    title: str
    scheduled_time: time
    scheduled_date: date | None
    repeat_days: str | None
    start_date: date | None
    created_at: datetime

    @property
    def is_recurring(self) -> bool:
        return self.repeat_days is not None


class ScheduleOccurrence(SQLModel):
    """특정 날짜에 실제로 표시할 일정 하나.

    반복 일정은 규칙 하나가 여러 날에 나타나므로, 화면이 그대로 그릴 수 있게
    서버가 날짜별로 펼쳐서 내려준다. is_done도 그 날짜 기준이다.
    """

    schedule_id: int
    type: ScheduleType
    title: str
    date: date
    scheduled_time: time
    is_done: bool
    is_recurring: bool


class ScheduleDoneUpdate(SQLModel):
    """특정 날짜의 이행 여부 변경."""

    date: date
    is_done: bool


class StepGoalUpdate(SQLModel):
    # 상한을 두는 이유는 잘못 누른 자릿수를 걸러내기 위해서다. 하루 10만 걸음은
    # 70km 남짓이라 목표로 잡을 값이 아니다.
    daily_goal: int = Field(ge=1, le=100_000)


class StepGoalResponse(SQLModel):
    daily_goal: int


class StepRecordUpsert(SQLModel):
    steps: int = Field(ge=0)


class StepRecordResponse(SQLModel):
    record_date: date
    steps: int
