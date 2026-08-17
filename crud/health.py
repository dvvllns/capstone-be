from datetime import date, timedelta

from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from models.health import (
    Schedule,
    ScheduleCompletion,
    ScheduleType,
    StepGoal,
    StepRecord,
)
from schemas.health import ScheduleCreate, ScheduleUpdate


# ── 일정 ──────────────────────────────────────────────────────────────────────

def create_schedule(
    session: Session, user_id: int, data: ScheduleCreate
) -> Schedule:
    schedule = Schedule(
        user_id=user_id,
        type=data.type,
        title=data.title,
        scheduled_time=data.scheduled_time,
        scheduled_date=data.scheduled_date,
        repeat_days=data.repeat_days,
        # 반복 일정에 시작일을 안 주면 오늘부터로 본다.
        start_date=data.start_date
        or (date.today() if data.repeat_days else None),
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def get_schedule(session: Session, schedule_id: int) -> Schedule | None:
    return session.get(Schedule, schedule_id)


def get_schedules(
    session: Session,
    user_id: int,
    *,
    type: ScheduleType | None = None,
) -> list[Schedule]:
    """저장된 일정 규칙 목록. 반복 일정은 펼치지 않은 원본이다."""
    statement = (
        select(Schedule)
        .where(col(Schedule.user_id) == user_id)
        .order_by(col(Schedule.scheduled_time).asc())
    )
    if type is not None:
        statement = statement.where(col(Schedule.type) == type)
    return list(session.exec(statement).all())


def update_schedule(
    session: Session, schedule: Schedule, data: ScheduleUpdate
) -> Schedule:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(schedule, key, value)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def delete_schedule(session: Session, schedule: Schedule) -> None:
    session.delete(schedule)
    session.commit()


def _occurs_on(schedule: Schedule, day: date) -> bool:
    """그 일정이 해당 날짜에 울리는지."""
    if schedule.scheduled_date is not None:
        return schedule.scheduled_date == day

    if not schedule.repeat_days:
        return False
    if schedule.start_date and day < schedule.start_date:
        return False
    return str(day.isoweekday()) in schedule.repeat_days.split(",")


def get_occurrences(
    session: Session, user_id: int, date_from: date, date_to: date
) -> list[dict]:
    """기간 안에 실제로 표시할 일정들을 날짜별로 펼친다.

    반복 일정은 규칙 하나가 여러 날에 나타나므로 화면이 그대로 그릴 수 있도록
    서버가 펼쳐서 내려준다. 완료 여부도 그 날짜 기준으로 채운다.
    """
    schedules = get_schedules(session, user_id)
    if not schedules:
        return []

    done = get_completions(
        session, [s.id for s in schedules if s.id is not None], date_from, date_to
    )

    occurrences: list[dict] = []
    day = date_from
    while day <= date_to:
        for schedule in schedules:
            if not _occurs_on(schedule, day):
                continue
            occurrences.append(
                {
                    "schedule_id": schedule.id,
                    "type": schedule.type,
                    "title": schedule.title,
                    "date": day,
                    "scheduled_time": schedule.scheduled_time,
                    "is_done": (schedule.id, day) in done,
                    "is_recurring": schedule.repeat_days is not None,
                }
            )
        day += timedelta(days=1)

    occurrences.sort(key=lambda o: (o["date"], o["scheduled_time"]))
    return occurrences


def get_completions(
    session: Session, schedule_ids: list[int], date_from: date, date_to: date
) -> set[tuple[int, date]]:
    """기간 안의 이행 기록. (일정 id, 날짜) 집합으로 돌려준다."""
    if not schedule_ids:
        return set()

    statement = (
        select(ScheduleCompletion.schedule_id, ScheduleCompletion.completed_date)
        .where(col(ScheduleCompletion.schedule_id).in_(schedule_ids))
        .where(col(ScheduleCompletion.completed_date) >= date_from)
        .where(col(ScheduleCompletion.completed_date) <= date_to)
    )
    return set(session.exec(statement).all())


def set_completion(
    session: Session, schedule_id: int, day: date, is_done: bool
) -> None:
    """특정 날짜의 이행 여부를 바꾼다.

    완료를 일정이 아니라 (일정, 날짜)에 붙여, 오늘 먹은 약이 내일까지
    완료로 남지 않게 한다.
    """
    existing = session.get(ScheduleCompletion, (schedule_id, day))
    if is_done and not existing:
        session.add(
            ScheduleCompletion(schedule_id=schedule_id, completed_date=day)
        )
        session.commit()
    elif not is_done and existing:
        session.delete(existing)
        session.commit()


# ── 걸음수 목표 ────────────────────────────────────────────────────────────────

def get_step_goal(session: Session, user_id: int) -> StepGoal | None:
    return session.get(StepGoal, user_id)


def upsert_step_goal(session: Session, user_id: int, daily_goal: int) -> StepGoal:
    existing = session.get(StepGoal, user_id)
    if existing:
        existing.daily_goal = daily_goal
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    goal = StepGoal(user_id=user_id, daily_goal=daily_goal)
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


# ── 걸음수 기록 ────────────────────────────────────────────────────────────────

def upsert_step_record(session: Session, user_id: int, record_date: date, steps: int) -> StepRecord:
    existing = session.get(StepRecord, (user_id, record_date))
    if existing:
        existing.steps = steps
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    record = StepRecord(user_id=user_id, record_date=record_date, steps=steps)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_step_records(
    session: Session,
    user_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[StepRecord]:
    statement = (
        select(StepRecord)
        .where(col(StepRecord.user_id) == user_id)
        .order_by(col(StepRecord.record_date).asc())
    )
    if date_from is not None:
        statement = statement.where(col(StepRecord.record_date) >= date_from)
    if date_to is not None:
        statement = statement.where(col(StepRecord.record_date) <= date_to)
    return list(session.exec(statement).all())


def delete_schedules_like(
    session: Session, user_id: int, schedule_ids: list[int]
) -> int:
    """고른 일정들과 제목·시각이 같은 일정을 모두 지우고 지운 수를 돌려준다.

    id만 받고 제목·시각은 서버가 찾아 쓴다. 앱이 보낸 제목을 그대로 믿으면
    화면에 없는 일정까지 지워달라고 할 수 있다.

    본인 것만 지운다. 남의 id나 없는 id는 조용히 건너뛴다. 다른 기기에서
    이미 지운 일정을 고른 경우까지 통째로 거절하면 아무것도 못 지운다.
    """
    targets = session.exec(
        select(Schedule)
        .where(col(Schedule.user_id) == user_id)
        .where(col(Schedule.id).in_(schedule_ids))
    ).all()
    if not targets:
        return 0

    signatures = {(t.title, t.scheduled_time) for t in targets}
    matched = session.exec(
        select(Schedule)
        .where(col(Schedule.user_id) == user_id)
        .where(
            or_(
                *[
                    and_(
                        col(Schedule.title) == title,
                        col(Schedule.scheduled_time) == when,
                    )
                    for title, when in signatures
                ]
            )
        )
    ).all()

    for schedule in matched:
        session.delete(schedule)
    session.commit()
    return len(matched)
