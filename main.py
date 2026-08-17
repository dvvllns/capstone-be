from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import BASE_DIR, settings
from routers import admin, chat, comments, gemini, groups, health, login, posts, user

app = FastAPI()
# 실행 위치가 아니라 프로젝트 폴더를 기준으로 삼는다. systemd나 cron에서
# 다른 디렉터리로 띄워도 같은 곳을 가리킨다.
app.mount(
    "/uploads", StaticFiles(directory=BASE_DIR / "uploads", html=False), name="uploads"
)

"""
app.add_middleware(
    CORSMiddleware,
    #수정해야됨 allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""

app.include_router(login.router)
app.include_router(user.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(admin.router)
app.include_router(groups.router)
app.include_router(chat.router)
app.include_router(health.router)
app.include_router(gemini.router)
