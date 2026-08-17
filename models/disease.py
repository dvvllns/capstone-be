from enum import StrEnum
from typing import NamedTuple

from sqlmodel import AutoString, Field, SQLModel


class DiseaseCategory(StrEnum):
    """진료 분과. 목록이 길어 화면에서 묶음 제목으로 쓴다."""

    CARDIO_METABOLIC = "cardio_metabolic"
    MUSCULOSKELETAL = "musculoskeletal"
    DIGESTIVE = "digestive"
    RESPIRATORY = "respiratory"
    KIDNEY_UROLOGY = "kidney_urology"
    ENDOCRINE = "endocrine"
    EYE_EAR = "eye_ear"
    NEURO_PSYCH = "neuro_psych"
    DENTAL = "dental"
    CANCER = "cancer"


CATEGORY_LABELS: dict[DiseaseCategory, str] = {
    DiseaseCategory.CARDIO_METABOLIC: "심혈관·대사",
    DiseaseCategory.MUSCULOSKELETAL: "근골격계",
    DiseaseCategory.DIGESTIVE: "소화기·간",
    DiseaseCategory.RESPIRATORY: "호흡기·수면",
    DiseaseCategory.KIDNEY_UROLOGY: "신장·비뇨기",
    DiseaseCategory.ENDOCRINE: "내분비",
    DiseaseCategory.EYE_EAR: "눈·귀",
    DiseaseCategory.NEURO_PSYCH: "신경·정신",
    DiseaseCategory.DENTAL: "치과",
    DiseaseCategory.CANCER: "암",
}


class DiseaseCode(StrEnum):
    """현재 앓고 있는 질환으로 고를 수 있는 항목.

    자유 입력 대신 코드로 받는다. 표기가 흔들리면 집계도 검색도 안 되고,
    자유 입력란에는 병원명이나 의사 이름까지 적히기 쉽다. 민감정보를 필요
    이상으로 모으지 않는 편이 낫다.

    "현재 앓고 있는" 것만 받으므로, 급성으로 지나가고 뒤에 상태만 남는
    질환은 표시명을 상태로 적었다(뇌졸중 후유증, 심근경색 병력). 그러지
    않으면 정작 중요한 항목을 아무도 고를 수 없다.
    """

    # 심혈관·대사
    HYPERTENSION = "hypertension"
    DIABETES = "diabetes"
    DYSLIPIDEMIA = "dyslipidemia"
    OBESITY = "obesity"
    CORONARY_ARTERY_DISEASE = "coronary_artery_disease"
    MYOCARDIAL_INFARCTION = "myocardial_infarction"
    ARRHYTHMIA = "arrhythmia"
    HEART_FAILURE = "heart_failure"
    STROKE = "stroke"
    # 근골격계
    OSTEOARTHRITIS = "osteoarthritis"
    OSTEOPOROSIS = "osteoporosis"
    RHEUMATOID_ARTHRITIS = "rheumatoid_arthritis"
    HERNIATED_DISC = "herniated_disc"
    SPINAL_STENOSIS = "spinal_stenosis"
    GOUT = "gout"
    # 소화기·간
    GERD = "gerd"
    CHRONIC_GASTRITIS = "chronic_gastritis"
    FATTY_LIVER = "fatty_liver"
    CHRONIC_HEPATITIS = "chronic_hepatitis"
    LIVER_CIRRHOSIS = "liver_cirrhosis"
    GALLSTONES = "gallstones"
    IBS = "ibs"
    # 호흡기·수면
    ASTHMA = "asthma"
    COPD = "copd"
    SLEEP_APNEA = "sleep_apnea"
    # 신장·비뇨기
    CHRONIC_KIDNEY_DISEASE = "chronic_kidney_disease"
    URINARY_STONE = "urinary_stone"
    BENIGN_PROSTATIC_HYPERPLASIA = "benign_prostatic_hyperplasia"
    URINARY_INCONTINENCE = "urinary_incontinence"
    # 내분비
    HYPOTHYROIDISM = "hypothyroidism"
    HYPERTHYROIDISM = "hyperthyroidism"
    # 눈·귀
    CATARACT = "cataract"
    GLAUCOMA = "glaucoma"
    MACULAR_DEGENERATION = "macular_degeneration"
    DIABETIC_RETINOPATHY = "diabetic_retinopathy"
    HEARING_LOSS = "hearing_loss"
    # 신경·정신
    DEMENTIA_OR_MCI = "dementia_or_mci"
    PARKINSONS_DISEASE = "parkinsons_disease"
    DEPRESSION = "depression"
    ANXIETY_DISORDER = "anxiety_disorder"
    # 치과
    PERIODONTAL_DISEASE = "periodontal_disease"
    TOOTH_LOSS = "tooth_loss"
    # 암
    CANCER = "cancer"


class DiseaseMeta(NamedTuple):
    label: str
    category: DiseaseCategory
    # "A"는 첫 화면에 바로 보여줄 만큼 흔한 것, 나머지는 더보기 안에 둔다.
    # 지금은 "A"와 "B"만 쓴다.
    priority: str


_C = DiseaseCategory

DISEASE_META: dict[DiseaseCode, DiseaseMeta] = {
    # 심혈관·대사
    DiseaseCode.HYPERTENSION: DiseaseMeta("고혈압", _C.CARDIO_METABOLIC, "A"),
    DiseaseCode.DIABETES: DiseaseMeta("당뇨병", _C.CARDIO_METABOLIC, "A"),
    DiseaseCode.DYSLIPIDEMIA: DiseaseMeta("고지혈증", _C.CARDIO_METABOLIC, "A"),
    DiseaseCode.OBESITY: DiseaseMeta("비만", _C.CARDIO_METABOLIC, "A"),
    DiseaseCode.CORONARY_ARTERY_DISEASE: DiseaseMeta("협심증·관상동맥질환", _C.CARDIO_METABOLIC, "B"),
    DiseaseCode.MYOCARDIAL_INFARCTION: DiseaseMeta("심근경색 병력", _C.CARDIO_METABOLIC, "B"),
    DiseaseCode.ARRHYTHMIA: DiseaseMeta("부정맥", _C.CARDIO_METABOLIC, "B"),
    DiseaseCode.HEART_FAILURE: DiseaseMeta("심부전", _C.CARDIO_METABOLIC, "B"),
    DiseaseCode.STROKE: DiseaseMeta("뇌졸중 후유증", _C.CARDIO_METABOLIC, "A"),
    # 근골격계
    DiseaseCode.OSTEOARTHRITIS: DiseaseMeta("퇴행성관절염", _C.MUSCULOSKELETAL, "A"),
    DiseaseCode.OSTEOPOROSIS: DiseaseMeta("골다공증", _C.MUSCULOSKELETAL, "A"),
    DiseaseCode.RHEUMATOID_ARTHRITIS: DiseaseMeta("류마티스관절염", _C.MUSCULOSKELETAL, "B"),
    DiseaseCode.HERNIATED_DISC: DiseaseMeta("목·허리 디스크", _C.MUSCULOSKELETAL, "A"),
    DiseaseCode.SPINAL_STENOSIS: DiseaseMeta("척추관협착증", _C.MUSCULOSKELETAL, "B"),
    DiseaseCode.GOUT: DiseaseMeta("통풍", _C.MUSCULOSKELETAL, "A"),
    # 소화기·간
    DiseaseCode.GERD: DiseaseMeta("역류성 식도염", _C.DIGESTIVE, "A"),
    DiseaseCode.CHRONIC_GASTRITIS: DiseaseMeta("만성위염", _C.DIGESTIVE, "B"),
    DiseaseCode.FATTY_LIVER: DiseaseMeta("지방간", _C.DIGESTIVE, "A"),
    DiseaseCode.CHRONIC_HEPATITIS: DiseaseMeta("만성간염", _C.DIGESTIVE, "B"),
    DiseaseCode.LIVER_CIRRHOSIS: DiseaseMeta("간경변", _C.DIGESTIVE, "B"),
    DiseaseCode.GALLSTONES: DiseaseMeta("담석증", _C.DIGESTIVE, "B"),
    DiseaseCode.IBS: DiseaseMeta("과민성대장증후군", _C.DIGESTIVE, "B"),
    # 호흡기·수면
    DiseaseCode.ASTHMA: DiseaseMeta("천식", _C.RESPIRATORY, "A"),
    DiseaseCode.COPD: DiseaseMeta("만성폐쇄성폐질환", _C.RESPIRATORY, "B"),
    DiseaseCode.SLEEP_APNEA: DiseaseMeta("수면무호흡증", _C.RESPIRATORY, "B"),
    # 신장·비뇨기
    DiseaseCode.CHRONIC_KIDNEY_DISEASE: DiseaseMeta("만성신장질환", _C.KIDNEY_UROLOGY, "A"),
    DiseaseCode.URINARY_STONE: DiseaseMeta("요로결석·신장결석", _C.KIDNEY_UROLOGY, "B"),
    DiseaseCode.BENIGN_PROSTATIC_HYPERPLASIA: DiseaseMeta("전립선비대증", _C.KIDNEY_UROLOGY, "A"),
    DiseaseCode.URINARY_INCONTINENCE: DiseaseMeta("요실금", _C.KIDNEY_UROLOGY, "B"),
    # 내분비
    DiseaseCode.HYPOTHYROIDISM: DiseaseMeta("갑상선기능저하증", _C.ENDOCRINE, "A"),
    DiseaseCode.HYPERTHYROIDISM: DiseaseMeta("갑상선기능항진증", _C.ENDOCRINE, "B"),
    # 눈·귀
    DiseaseCode.CATARACT: DiseaseMeta("백내장", _C.EYE_EAR, "A"),
    DiseaseCode.GLAUCOMA: DiseaseMeta("녹내장", _C.EYE_EAR, "A"),
    DiseaseCode.MACULAR_DEGENERATION: DiseaseMeta("황반변성", _C.EYE_EAR, "B"),
    DiseaseCode.DIABETIC_RETINOPATHY: DiseaseMeta("당뇨망막병증", _C.EYE_EAR, "B"),
    DiseaseCode.HEARING_LOSS: DiseaseMeta("난청", _C.EYE_EAR, "B"),
    # 신경·정신
    DiseaseCode.DEMENTIA_OR_MCI: DiseaseMeta("치매·경도인지장애", _C.NEURO_PSYCH, "B"),
    DiseaseCode.PARKINSONS_DISEASE: DiseaseMeta("파킨슨병", _C.NEURO_PSYCH, "B"),
    DiseaseCode.DEPRESSION: DiseaseMeta("우울증", _C.NEURO_PSYCH, "B"),
    DiseaseCode.ANXIETY_DISORDER: DiseaseMeta("불안장애", _C.NEURO_PSYCH, "B"),
    # 치과
    DiseaseCode.PERIODONTAL_DISEASE: DiseaseMeta("치주질환(잇몸병)", _C.DENTAL, "A"),
    DiseaseCode.TOOTH_LOSS: DiseaseMeta("틀니·임플란트 사용", _C.DENTAL, "B"),
    # 암
    # 암 종류를 나누지 않는 이유는, 앱이 종류에 따라 다르게 행동할 수 없기
    # 때문이다. 치료 중이라는 사실 하나만 알면 조언 수위를 낮출 수 있고,
    # 그 이상은 담당 의료진의 몫이다.
    DiseaseCode.CANCER: DiseaseMeta("암 (현재 치료 중)", _C.CANCER, "B"),
}

# 이름만 쓰는 곳이 많아 따로 둔다.
DISEASE_LABELS: dict[DiseaseCode, str] = {
    code: meta.label for code, meta in DISEASE_META.items()
}


class UserDisease(SQLModel, table=True):
    """사용자가 선택한 기저질환.

    별도 테이블인 이유는 한 사람이 여러 개를 가지기 때문이다. 당뇨와 고혈압을
    함께 앓는 경우가 흔하다. 나중에 진단 시기나 중증도를 붙이고 싶어지면
    컬럼만 더하면 된다.

    건강 정보는 민감정보다. 이 값은 본인만 조회할 수 있어야 하며,
    UserResponse처럼 남에게 나가는 응답에 절대 넣지 않는다.
    """

    __tablename__ = "user_disease"

    user_id: int = Field(foreign_key="user.id", primary_key=True)
    code: DiseaseCode = Field(primary_key=True, sa_type=AutoString())
