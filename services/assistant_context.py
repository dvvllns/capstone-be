from datetime import date, timedelta

from sqlmodel import Session

from crud import disease as disease_crud
from crud import group as group_crud
from crud import health as health_crud
from models import User
from models.disease import DISEASE_LABELS
from schemas.gemini import AssistantTopic

# 프롬프트에 넣을 양의 상한. 길수록 비용과 지연이 늘고, 정작 필요한 내용이
# 묻히기도 한다.
MAX_SCHEDULES = 8
MAX_GROUPS = 5
STEP_LOOKBACK_DAYS = 7


def build_user_context(
    session: Session,
    user: User,
    today: date | None = None,
    topic: AssistantTopic = AssistantTopic.GENERAL,
) -> str:
    """도우미에게 넘길 회원 정보를 사람이 읽는 문장으로 만든다.

    반드시 [user] 본인 것만 모은다. 다른 사람의 정보가 섞이면 그대로 답변에
    새어 나간다.

    JSON 대신 문장으로 만드는 이유는, 모델이 이 값을 '사실'로 읽고 답변에
    자연스럽게 녹여 쓰기 때문이다. 중괄호가 많으면 지시문처럼 해석하기도 한다.

    [topic]이 FOOD이면 걸음수·일정·모임을 넣지 않는다. 음식을 물었는데
    가입한 모임 목록까지 붙일 이유가 없고, 쓸데없는 값이 많으면 정작
    중요한 질환 정보가 묻힌다.
    """
    assert user.id is not None
    day = today or date.today()
    lines: list[str] = []

    lines.append(f"- 호칭: {user.nickname}님")
    age = _age(user.date_of_birth, day)
    if age is not None:
        lines.append(f"- 나이: 만 {age}세")

    codes = disease_crud.get_user_diseases(session, user.id)
    if codes:
        names = ", ".join(DISEASE_LABELS[c] for c in codes)
        lines.append(f"- 앓고 있는 질환: {names}")
    else:
        lines.append("- 앓고 있는 질환: 등록하지 않음")

    if topic is not AssistantTopic.FOOD:
        lines.append(_steps_line(session, user.id, day))
        lines.extend(_schedule_lines(session, user.id, day))
        lines.append(_groups_line(session, user.id))

    return "\n".join(lines)


def _age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years if years >= 0 else None


def _steps_line(session: Session, user_id: int, today: date) -> str:
    records = health_crud.get_step_records(
        session, user_id, today - timedelta(days=STEP_LOOKBACK_DAYS - 1), today
    )
    if not records:
        return "- 걸음수: 기록 없음"

    by_day = {r.record_date: r.steps for r in records}
    today_steps = by_day.get(today)
    average = sum(by_day.values()) // len(by_day)

    goal = health_crud.get_step_goal(session, user_id)
    parts = [
        f"오늘 {today_steps:,}보" if today_steps is not None else "오늘 기록 없음",
        f"최근 {len(by_day)}일 평균 {average:,}보",
    ]
    if goal is not None:
        parts.append(f"목표 {goal.daily_goal:,}보")
    return "- 걸음수: " + ", ".join(parts)


def _schedule_lines(session: Session, user_id: int, today: date) -> list[str]:
    occurrences = health_crud.get_occurrences(session, user_id, today, today)
    if not occurrences:
        return ["- 오늘 일정: 없음"]

    lines = ["- 오늘 일정:"]
    for item in occurrences[:MAX_SCHEDULES]:
        when = item["scheduled_time"].strftime("%H:%M")
        state = "완료" if item["is_done"] else "아직"
        lines.append(f"    · {when} {item['title']} ({state})")
    if len(occurrences) > MAX_SCHEDULES:
        lines.append(f"    · 그 밖에 {len(occurrences) - MAX_SCHEDULES}건 더 있음")
    return lines


def _groups_line(session: Session, user_id: int) -> str:
    groups = group_crud.get_my_groups(session, user_id, limit=MAX_GROUPS)
    if not groups:
        return "- 가입한 모임: 없음"
    return "- 가입한 모임: " + ", ".join(g.name for g in groups)
