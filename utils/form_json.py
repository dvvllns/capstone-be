from typing import TypeVar

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def parse_form_json(model: type[ModelT], raw: str) -> ModelT:
    """multipart 폼에 JSON 문자열로 실려온 값을 스키마로 검증한다.

    핸들러 본문에서 model_validate_json을 그대로 호출하면 ValidationError가
    처리되지 않은 예외가 되어 500이 된다. FastAPI가 요청 파싱 단계에서 쓰는
    예외로 바꿔, 평범한 JSON 본문을 받을 때와 똑같이 422와 detail 배열을
    응답하게 한다.
    """
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
