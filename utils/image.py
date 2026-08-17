import uuid
from datetime import datetime, timezone
from pathlib import Path

import pyvips
from fastapi import HTTPException, UploadFile, status

BASE_UPLOAD_DIR = Path("uploads/images")
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
    path = Path(url)
    if path.exists():
        path.unlink()
