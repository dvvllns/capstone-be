from enum import StrEnum

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from services.gemini import MAX_QUESTION_LENGTH


class AssistantTopic(StrEnum):
    """질문의 성격. 회원 정보를 어디까지 붙일지 정하는 데 쓴다."""

    GENERAL = "general"
    FOOD = "food"


class FoodRecognitionResponse(SQLModel):
    """음식 사진 인식 결과"""

    foods: list[str]


class AssistantRequest(SQLModel):
    """앱 도우미에게 보내는 질문"""

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    # 예전 앱은 이 값을 보내지 않으므로 기본값을 둔다.
    topic: AssistantTopic = AssistantTopic.GENERAL

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("질문을 입력해주세요")
        return stripped


class AssistantResponse(SQLModel):
    answer: str
