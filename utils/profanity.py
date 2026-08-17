"""욕설 검사.

한국어는 korcen, 영어는 better_profanity가 맡는다. 둘 다 쓰는 이유는
서로 못 잡는 쪽이 있어서다. korcen은 영어 욕을, better_profanity는 한국어를
전혀 걸러내지 못한다.

korcen 1.0.3은 패턴이 534개나 되지만 정작 흔한 표기를 여럿 빠뜨린다.
그래서 아래 목록으로 메운다.
"""

import re

from better_profanity import profanity

from korcen import korcen

# 사전을 한 번만 읽는다. 요청마다 부르면 느리다.
profanity.load_censor_words()

# korcen이 놓치는 표현들.
# 정상 단어에 섞일 수 있는 말은 일부러 뺐다.
EXTRA_PROFANITY: tuple[str, ...] = (
    # 기본형
    "씨발", "씹새", "존나", "존내", "죤나", "졸라", "븅신", "등신",
    "멍청이", "후레", "호로",
    # 축약·초성
    "ㄲㅈ", "ㅅㅍ", "ㅈㄲ", "ㅆㄺ",
    # 비하
    "틀딱", "맘충",
    # 성적
    "꼴리", "야동", "떡치",
    # 그 밖
    "엿먹", "개수작",
)

_EXTRA_REGEX = re.compile("|".join(map(re.escape, EXTRA_PROFANITY)))

# 글자와 숫자만 남긴다. 사이에 끼운 공백이나 기호로 빠져나가는 것을 막는다.
_NON_ALNUM = re.compile(r"[^0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]")
_DIGITS = re.compile(r"[0-9]")


def contains_profanity(text: str) -> bool:
    """욕설이 들어 있으면 True.

    있는 그대로 한 번 보고, 걸리지 않으면 기호와 숫자를 뺀 모양으로 다시
    본다. "시 발", "시*발", "시1발" 같은 우회가 흔하기 때문이다.

    유니코드 정규화(NFKC)는 하지 않는다. 초성이 다른 글자로 바뀌어
    "ㅅㅂ" 같은 표현을 오히려 놓친다.
    """
    if not text:
        return False

    if _check(text):
        return True

    squashed = _NON_ALNUM.sub("", text)
    if squashed != text and _check(squashed):
        return True

    no_digits = _DIGITS.sub("", squashed)
    return no_digits != squashed and _check(no_digits)


def _check(value: str) -> bool:
    if _EXTRA_REGEX.search(value):
        return True
    if korcen.check(value):
        return True
    return profanity.contains_profanity(value)
