from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel import Session

from database import get_session
from dependencies import get_current_user
from models import User
from schemas import AssistantRequest, AssistantResponse, FoodRecognitionResponse
from services import assistant_context
from services import gemini as gemini_service
from services.rate_limit import check_rate_limit
from utils.image import MAX_FILE_SIZE

router = APIRouter(prefix="/gemini", tags=["gemini"])

FOOD_RECOGNITION_COOLDOWN_SECONDS = 5
MAX_FOOD_RECOGNITIONS_PER_WINDOW = 30
FOOD_RECOGNITION_WINDOW_SECONDS = 10 * 60

ASSISTANT_COOLDOWN_SECONDS = 3
MAX_ASSISTANT_CALLS_PER_WINDOW = 40
ASSISTANT_WINDOW_SECONDS = 10 * 60


@router.post("/assistant", response_model=AssistantResponse)
def ask_assistant(
    body: AssistantRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """앱 도우미에게 질문한다.

    Gemini 호출을 서버가 대신하는 이유는 두 가지다. 앱에 API 키를 넣으면
    APK를 뜯어 꺼낼 수 있고, 답변에 쓸 회원 정보는 어차피 서버에만 있다.
    """
    assert current_user.id is not None
    check_rate_limit(
        f"assistant_rate:{current_user.id}",
        cooldown_seconds=ASSISTANT_COOLDOWN_SECONDS,
        max_count=MAX_ASSISTANT_CALLS_PER_WINDOW,
        window_seconds=ASSISTANT_WINDOW_SECONDS,
        cooldown_message="{wait}초 후 다시 시도해주세요",
        limit_message="질문이 너무 많습니다. 잠시 후 다시 시도해주세요",
    )

    # 답변에 쓸 회원 정보는 반드시 본인 것만 모은다.
    user_context = assistant_context.build_user_context(
        session, current_user, topic=body.topic
    )

    try:
        answer = gemini_service.ask_assistant(body.question, user_context)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="답변을 가져오지 못했습니다. 잠시 후 다시 시도해주세요",
        )

    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="답변을 가져오지 못했습니다. 잠시 후 다시 시도해주세요",
        )
    return {"answer": answer}


@router.post("/food-recognition", response_model=FoodRecognitionResponse)
def recognize_food(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
):
    """음식 사진 속 음식 이름을 한국어로 인식"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지 파일만 업로드 가능합니다",
        )
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="파일 크기는 20MB를 초과할 수 없습니다",
        )

    assert current_user.id is not None
    check_rate_limit(
        f"food_recognition_rate:{current_user.id}",
        cooldown_seconds=FOOD_RECOGNITION_COOLDOWN_SECONDS,
        max_count=MAX_FOOD_RECOGNITIONS_PER_WINDOW,
        window_seconds=FOOD_RECOGNITION_WINDOW_SECONDS,
        cooldown_message="{wait}초 후 다시 시도해주세요",
        limit_message="요청 횟수를 초과했습니다. 잠시 후 다시 시도해주세요",
    )

    data = file.file.read()
    try:
        foods = gemini_service.recognize_food(data, file.content_type)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="이미지 분석에 실패했습니다"
        )
    return {"foods": foods}
