from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from crud import disease as disease_crud
from crud import health as health_crud
from database import get_session
from dependencies import get_current_user
from models import User
from models.disease import CATEGORY_LABELS, DISEASE_META, DiseaseCode
from models.health import ScheduleType
from schemas import (
    DiseaseOption,
    UserDiseaseResponse,
    UserDiseaseUpdate,
    ScheduleBulkDelete,
    ScheduleBulkDeleteResult,
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
    ScheduleDoneUpdate,
    ScheduleOccurrence,
    StepGoalResponse,
    StepGoalUpdate,
    StepRecordResponse,
    StepRecordUpsert,
)

router = APIRouter(prefix="/health", tags=["health"])

# 반복 일정을 펼치므로 한 번에 너무 긴 기간을 요청하지 못하게 막는다.
MAX_OCCURRENCE_RANGE_DAYS = 92


# ── 기저질환 ──────────────────────────────────────────────────────────────────


@router.get("/diseases", response_model=list[DiseaseOption])
def list_disease_options(_: User = Depends(get_current_user)):
    """선택 가능한 기저질환 목록.

    앱에 목록을 박아두지 않고 서버가 주는 이유는, 항목을 늘릴 때 앱 배포를
    기다리지 않아도 되고 저장 시 유효성 검사와 기준이 어긋나지 않기 때문이다.

    정의된 순서 그대로 내려보낸다. 분과끼리 묶여 있어 화면이 따로 정렬할
    필요가 없다.
    """
    return [
        {
            "code": code,
            "label": meta.label,
            "category": meta.category,
            "category_label": CATEGORY_LABELS[meta.category],
            "priority": meta.priority,
        }
        for code, meta in DISEASE_META.items()
    ]


@router.get("/me/diseases", response_model=UserDiseaseResponse)
def get_my_diseases(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내 기저질환 조회.

    건강 정보는 민감정보라 본인만 볼 수 있어야 한다. 그래서 UserResponse에
    넣지 않고 이 경로로 따로 뺐다.
    """
    assert current_user.id is not None
    return {"codes": disease_crud.get_user_diseases(session, current_user.id)}


@router.put("/me/diseases", response_model=UserDiseaseResponse)
def set_my_diseases(
    body: UserDiseaseUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내 기저질환을 선택한 목록으로 교체한다."""
    assert current_user.id is not None
    return {"codes": disease_crud.set_user_diseases(session, current_user.id, body.codes)}


# ── 일정 ──────────────────────────────────────────────────────────────────────

@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """복약 또는 약속 일정 등록"""
    assert current_user.id is not None
    return health_crud.create_schedule(session, current_user.id, body)


@router.get("/schedules", response_model=list[ScheduleResponse])
def list_schedules(
    type: ScheduleType | None = Query(default=None, description="medication | appointment"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """등록한 일정 규칙 목록 (반복 일정은 펼치지 않은 원본)"""
    assert current_user.id is not None
    return health_crud.get_schedules(session, current_user.id, type=type)


@router.get("/schedules/occurrences", response_model=list[ScheduleOccurrence])
def list_occurrences(
    date_from: date = Query(description="조회 시작일"),
    date_to: date = Query(description="조회 종료일"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """기간 안에 실제로 표시할 일정들.

    반복 일정을 날짜별로 펼쳐서 내려주므로 화면은 그대로 그리기만 하면 된다.
    """
    assert current_user.id is not None
    if date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="종료일이 시작일보다 빠릅니다",
        )
    if (date_to - date_from).days > MAX_OCCURRENCE_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"한 번에 최대 {MAX_OCCURRENCE_RANGE_DAYS}일까지 조회할 수 있습니다",
        )
    return health_crud.get_occurrences(session, current_user.id, date_from, date_to)


@router.put(
    "/schedules/{schedule_id}/done", status_code=status.HTTP_204_NO_CONTENT
)
def set_schedule_done(
    schedule_id: int,
    body: ScheduleDoneUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """특정 날짜의 이행 여부 표시.

    반복 일정은 날마다 따로 체크해야 하므로 완료 여부를 날짜와 함께 받는다.
    """
    schedule = health_crud.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다")
    if schedule.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="수정 권한이 없습니다")
    health_crud.set_completion(session, schedule_id, body.date, body.is_done)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """일정 수정. 이행 여부는 날짜별이라 /done에서 따로 다룬다."""
    schedule = health_crud.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다")
    if schedule.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="수정 권한이 없습니다")
    return health_crud.update_schedule(session, schedule, body)


@router.delete("/schedules", response_model=ScheduleBulkDeleteResult)
def delete_schedules(
    body: ScheduleBulkDelete,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """고른 일정들과 제목·시각이 같은 일정을 한 번에 삭제한다.

    한 건씩 반복해서 지우면 중간에 실패했을 때 앞의 것만 지워진 채로 남고,
    사용자는 무엇이 지워졌는지 알 수 없다. 한 번에 처리한다.

    같은 이름·시각으로 여러 번 등록해둔 일정을 한꺼번에 정리하려는 기능이다.
    고른 것보다 많이 지워질 수 있어 앱이 미리 알려야 한다.
    """
    assert current_user.id is not None
    deleted = health_crud.delete_schedules_like(session, current_user.id, body.ids)
    return {"deleted": deleted}


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """일정 삭제"""
    schedule = health_crud.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="일정을 찾을 수 없습니다")
    if schedule.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="삭제 권한이 없습니다")
    health_crud.delete_schedule(session, schedule)


# ── 걸음수 목표 ────────────────────────────────────────────────────────────────

@router.get("/step-goal", response_model=StepGoalResponse)
def get_step_goal(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내 하루 목표 걸음수 조회"""
    assert current_user.id is not None
    goal = health_crud.get_step_goal(session, current_user.id)
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="목표 걸음수가 설정되지 않았습니다")
    return {"daily_goal": goal.daily_goal}


@router.put("/step-goal", response_model=StepGoalResponse)
def set_step_goal(
    body: StepGoalUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """하루 목표 걸음수 설정/변경"""
    assert current_user.id is not None
    goal = health_crud.upsert_step_goal(session, current_user.id, body.daily_goal)
    return {"daily_goal": goal.daily_goal}


# ── 걸음수 기록 ────────────────────────────────────────────────────────────────

@router.put("/steps/{record_date}", response_model=StepRecordResponse)
def upsert_steps(
    record_date: date,
    body: StepRecordUpsert,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """특정 날짜의 걸음수 기록 (없으면 생성, 있으면 덮어쓰기)"""
    assert current_user.id is not None
    record = health_crud.upsert_step_record(session, current_user.id, record_date, body.steps)
    return {"record_date": record.record_date, "steps": record.steps}


@router.get("/steps", response_model=list[StepRecordResponse])
def list_steps(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """날짜 범위로 걸음수 기록 조회"""
    assert current_user.id is not None
    records = health_crud.get_step_records(
        session, current_user.id, date_from=date_from, date_to=date_to
    )
    return [{"record_date": r.record_date, "steps": r.steps} for r in records]
