from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 프로젝트 폴더의 절대 경로. cron처럼 다른 위치에서 실행돼도 .env를 찾게 한다.
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    DATABASE_URL: str

    # JWT 설정
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # 자동 로그인 유지 기간. 이 기간 안에 앱을 한 번도 안 켜면 다시 로그인해야 한다.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Firebase
    FIREBASE_CREDENTIALS_PATH: str = "firebase-credentials.json"

    # Redis (OTP 등 TTL이 필요한 데이터 저장용)
    REDIS_URL: str

    # SOLAPI (휴대폰 인증번호 발송)
    SOLAPI_API_KEY: str
    SOLAPI_API_SECRET: str
    SOLAPI_SENDER_PHONE: str

    # Gemini (음식 사진 인식 등)
    GEMINI_API_KEY: str

    # 환경별 설정
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ["*"]

    # CORS 설정 추가?

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",  # 실행 위치와 무관하게 같은 파일을 읽는다
        env_file_encoding="utf-8",
    )


settings = Settings()
