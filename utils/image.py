import uuid
from datetime import datetime, timezone
from pathlib import Path

import pyvips
from fastapi import HTTPException, UploadFile, status

from config import BASE_DIR

# 프로젝트 폴더 기준으로 잡는다. 실행 위치를 기준으로 두면 cron이나 다른
# 디렉터리에서 부를 때 엉뚱한 곳을 보게 된다.
BASE_UPLOAD_DIR = BASE_DIR / "uploads" / "images"
MAX_DIMENSION = 1920
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def process_and_save_image(file: UploadFile, subdir: str) -> tuple[str, int]:
    """이미지 유효성 검사, 처리, 저장 후 URL 반환"""
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
    try:
        data = file.file.read()
        img = pyvips.Image.thumbnail_buffer(
            data,
            MAX_DIMENSION,
            height=MAX_DIMENSION,
            size=pyvips.enums.Size.DOWN,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이미지 처리에 실패했습니다"
        )

    date_path = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    upload_dir = BASE_UPLOAD_DIR / subdir / date_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.webp"
    saved_path = upload_dir / filename
    img.webpsave(str(saved_path), Q=85, strip=True)
    return f"uploads/images/{subdir}/{date_path}/{filename}", saved_path.stat().st_size


def delete_image(url: str) -> None:
    """저장된 url이 가리키는 파일을 지운다.

    url은 앱에 내려주는 주소이면서 동시에 저장 위치다. 파일을 만질 때만
    프로젝트 폴더 기준으로 풀어 쓴다. 앞의 슬래시를 떼는 이유는, 절대 경로를
    붙이면 pathlib이 앞부분을 버려서 프로젝트 밖을 가리키기 때문이다.
    """
    path = BASE_DIR / url.lstrip("/")
    if path.exists():
        path.unlink()
