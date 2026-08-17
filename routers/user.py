from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from crud import auth as auth_crud
from crud import comment as comment_crud
from crud import group as group_crud
from crud import post as post_crud
from crud import upload as upload_crud
from crud import user as user_crud
from database import get_session
from dependencies import get_current_user
from models import User
from schemas.user import NicknameRejection
from utils.profanity import contains_profanity
from models.user import DELETED_NICKNAME, RESERVED_NICKNAMES
from schemas import (
    BlockRequest,
    BlockedUserResponse,
    PasswordVerifyRequest,
    PhoneNumberUpdate,
    PhoneOTPRequest,
    PhoneOTPVerifyRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from services import otp as otp_service
from services import group_leave
from services import password_verify
from utils.form_json import parse_form_json
from utils.image import delete_image, process_and_save_image

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/phone/otp", status_code=status.HTTP_204_NO_CONTENT)
def send_signup_otp(payload: PhoneOTPRequest, session: Session = Depends(get_session)):
    """회원가입용 휴대폰 인증번호 발송"""
    if not user_crud.is_phone_number_available(session, payload.phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 휴대폰 번호입니다"
        )
    otp_service.send_otp(payload.phone_number, otp_service.OTPPurpose.SIGNUP)


@router.post("/phone/otp/verify", status_code=status.HTTP_204_NO_CONTENT)
def verify_signup_otp(payload: PhoneOTPVerifyRequest):
    """회원가입용 휴대폰 인증번호 검증.

    성공하면 인증 완료 상태가 서버에 기록되어, 이후 회원가입 요청에서
    인증번호를 다시 보내지 않아도 된다.
    """
    otp_service.verify_otp(
        payload.phone_number, otp_service.OTPPurpose.SIGNUP, payload.otp
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: str = Form(..., description="UserCreate JSON 문자열"),
    profile_pic: UploadFile | None = None,
    session: Session = Depends(get_session),
):
    """사용자 생성. user_data는 UserCreate 스키마의 JSON 문자열"""
    user_create = parse_form_json(UserCreate, user_data)
    if user_crud.get_user_by_login_id(session, user_create.login_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 ID입니다"
        )
    if not user_crud.is_phone_number_available(session, user_create.phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 휴대폰 번호입니다"
        )
    if not user_crud.is_nickname_available(session, user_create.nickname):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 닉네임입니다"
        )
    # 인증 표식은 1회용이므로, 실패할 수 있는 검사를 모두 통과한 뒤에 소비한다.
    otp_service.consume_verification(
        user_create.phone_number, otp_service.OTPPurpose.SIGNUP
    )
    profile_pic_url = None
    saved_size = None
    if profile_pic:
        profile_pic_url, saved_size = process_and_save_image(profile_pic, "profile")
    user = user_crud.create_user(session, user_create, profile_pic_url)
    if profile_pic_url:
        assert user.id is not None
        upload_crud.log_upload(session, user.id, saved_size, profile_pic_url)
    return user


@router.get("/check/login-id")
def check_login_id(value: str, session: Session = Depends(get_session)):
    """로그인 ID 중복 확인.

    UserBase.login_id_check가 가입 시 ID를 소문자로 바꾸므로 여기서도 똑같이
    맞춘다. 그러지 않으면 'ABC'가 사용 가능하다고 나온 뒤 가입에서 중복으로
    거부된다.
    """
    return {"available": user_crud.is_login_id_available(session, value.lower())}


@router.get("/check/nickname")
def check_nickname(value: str, session: Session = Depends(get_session)):
    """닉네임 사용 가능 여부.

    스키마의 str_strip_whitespace가 가입 시 앞뒤 공백을 제거하므로 여기서도
    동일하게 맞춘다. 예약어와 욕설도 가입 시 거부되므로 여기서 함께 걸러야
    "사용 가능"이라고 안내한 뒤 가입에서 실패하는 일이 없다.

    쓸 수 없는 이유를 [reason]으로 함께 준다. available만 주면 화면이 전부
    "이미 사용 중"으로 안내해, 욕설 때문에 막힌 사람이 이유를 알 수 없다.
    """
    nickname = value.strip()
    if nickname in RESERVED_NICKNAMES:
        return {"available": False, "reason": NicknameRejection.RESERVED}
    if contains_profanity(nickname):
        return {"available": False, "reason": NicknameRejection.PROFANITY}
    if not user_crud.is_nickname_available(session, nickname):
        return {"available": False, "reason": NicknameRejection.TAKEN}
    return {"available": True, "reason": None}


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    """현재 로그인한 사용자 정보 조회"""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """사용자 정보 수정 (프로필 사진 제외)"""
    old_nickname = current_user.nickname
    updated = user_crud.update_user(session, current_user, user_update)
    assert updated.id is not None

    if user_update.nickname is not None and user_update.nickname != old_nickname:
        post_crud.update_posts_nickname(session, updated.id, updated.nickname)
        comment_crud.update_comments_nickname(session, updated.id, updated.nickname)

    if user_update.password is not None:
        # 비밀번호를 바꾼 이유가 계정 도용일 수 있다. 다른 기기의 자동 로그인을
        # 모두 끊어 옛 비밀번호를 아는 사람이 계속 들어오지 못하게 한다.
        auth_crud.revoke_all_for_user(session, updated.id)

    return updated


@router.post("/me/phone/otp", status_code=status.HTTP_204_NO_CONTENT)
def send_phone_change_otp(
    payload: PhoneOTPRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """휴대폰 번호 변경용 인증번호 발송"""
    existing = user_crud.get_user_by_phone_number(session, payload.phone_number)
    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 휴대폰 번호입니다"
        )
    otp_service.send_otp(payload.phone_number, otp_service.OTPPurpose.CHANGE_PHONE)


@router.post("/me/phone/otp/verify", status_code=status.HTTP_204_NO_CONTENT)
def verify_phone_change_otp(
    payload: PhoneOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """휴대폰 번호 변경용 인증번호 검증"""
    otp_service.verify_otp(
        payload.phone_number, otp_service.OTPPurpose.CHANGE_PHONE, payload.otp
    )


@router.patch("/me/phone", response_model=UserResponse)
def update_phone_number(
    payload: PhoneNumberUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """휴대폰 번호 변경 (인증번호 검증 포함)"""
    existing = user_crud.get_user_by_phone_number(session, payload.phone_number)
    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 휴대폰 번호입니다"
        )
    otp_service.consume_verification(
        payload.phone_number, otp_service.OTPPurpose.CHANGE_PHONE
    )
    return user_crud.update_phone_number(session, current_user, payload.phone_number)


@router.put("/me/profile-pic", response_model=UserResponse)
def upload_profile_pic(
    file: UploadFile,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """프로필 사진 업로드 및 즉시 적용"""
    assert current_user.id is not None
    old_url = current_user.profile_pic
    if file.size:
        upload_crud.check_upload_limit(session, current_user.id, file.size)
    url, saved_size = process_and_save_image(file, "profile")
    upload_crud.log_upload(session, current_user.id, saved_size, url)
    result = user_crud.update_profile_pic(session, current_user, url)
    if old_url:
        delete_image(old_url)
        upload_crud.delete_log_by_url(session, old_url)
    return result


@router.get("/me/blocks", response_model=list[BlockedUserResponse])
def read_blocked_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """내가 차단한 사용자 목록"""
    assert current_user.id is not None
    return user_crud.get_blocked_users(session, current_user.id)


@router.post("/me/blocks", status_code=status.HTTP_204_NO_CONTENT)
def block_user(
    payload: BlockRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """닉네임으로 사용자 차단.

    앱에서는 상대의 내부 id를 알 수 없고 닉네임만 보이므로 닉네임을 받는다.
    """
    assert current_user.id is not None
    target_user = user_crud.get_user_by_nickname(session, payload.nickname)
    if not target_user or target_user.id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="본인을 차단할 수 없습니다"
        )
    if target_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="관리자는 차단할 수 없습니다"
        )
    user_crud.block_user(session, current_user.id, target_user.id)


@router.delete("/me/blocks/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """차단 해제. 목록에서 받은 id를 그대로 넘긴다."""
    assert current_user.id is not None
    user_crud.unblock_user(session, current_user.id, user_id)


@router.post("/me/verify-password", status_code=status.HTTP_204_NO_CONTENT)
def verify_current_password(
    payload: PasswordVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """현재 비밀번호 확인 (10분간 5회까지)"""
    assert current_user.id is not None
    password_verify.verify_current_password(
        current_user.id, current_user.hashed_password, payload.password
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(
    payload: PasswordVerifyRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """회원 탈퇴.

    작성한 게시글과 댓글은 남기고 계정만 탈퇴 처리한다. 탈퇴하면 전화번호와
    아이디, 닉네임이 풀려 같은 번호로 다시 가입할 수 있다.
    """
    assert current_user.id is not None
    password_verify.verify_current_password(
        current_user.id, current_user.hashed_password, payload.password
    )
    user_id = current_user.id

    _hand_over_or_delete_groups(session, user_id)

    # 게시글/댓글/채팅에는 작성 시점 닉네임이 복사돼 있어 따로 갱신해야
    # 표시가 익명화된다. 익명으로 쓴 글은 함수 안에서 건너뛴다.
    post_crud.update_posts_nickname(session, user_id, DELETED_NICKNAME)
    comment_crud.update_comments_nickname(session, user_id, DELETED_NICKNAME)
    comment_crud.update_chat_nickname(session, user_id, DELETED_NICKNAME)

    old_profile_pic = current_user.profile_pic
    user_crud.delete_user_personal_data(session, user_id)
    user_crud.anonymize_user(session, current_user)

    if old_profile_pic:
        delete_image(old_profile_pic)
        upload_crud.delete_log_by_url(session, old_profile_pic)


def _hand_over_or_delete_groups(session: Session, user_id: int) -> None:
    """탈퇴자가 모임장인 모임들을 정리한다(위임 또는 삭제)."""
    for group in group_crud.get_groups_led_by(session, user_id):
        group_leave.hand_over_or_delete(session, group, user_id)
