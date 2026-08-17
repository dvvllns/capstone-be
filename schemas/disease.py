from sqlmodel import Field, SQLModel

from models.disease import DiseaseCategory, DiseaseCode


class DiseaseOption(SQLModel):
    """앱이 칩으로 그릴 선택지.

    분과와 우선도를 함께 내려보내, 화면이 흔한 것부터 보여주고 나머지는
    분과별로 묶어 펼칠 수 있게 한다.
    """

    code: DiseaseCode
    label: str
    category: DiseaseCategory
    category_label: str
    # "A"면 첫 화면에 바로 보인다. "B"·"C"는 더보기 안에 들어간다.
    priority: str


class UserDiseaseResponse(SQLModel):
    """내가 선택한 기저질환. 본인에게만 나간다."""

    codes: list[DiseaseCode]


class UserDiseaseUpdate(SQLModel):
    """선택한 질환 전체를 보낸다. 서버는 이 목록으로 교체한다."""

    codes: list[DiseaseCode] = Field(max_length=len(DiseaseCode))
