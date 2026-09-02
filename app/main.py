"""FastAPI 진입점."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.core.config import settings
from app.web import router as web_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """로컬 개발 편의: SQLite일 때만 테이블 자동 생성.

    PostgreSQL(운영)은 Alembic 마이그레이션을 사용하므로 여기서 생성하지 않는다.
    """
    if settings.database_url.startswith("sqlite"):
        from app.core.database import Base, engine
        import app.models  # noqa: F401 - 모델 등록

        Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
)

# 정적 파일 (CSS 등)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 라우터: HTML 페이지 + JSON API
app.include_router(web_router)
app.include_router(api_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """헬스체크 — 컨테이너/로드밸런서용."""
    return {"status": "ok", "environment": settings.environment}
