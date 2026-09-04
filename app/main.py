"""FastAPI 진입점."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import router as api_router
from app.core.config import settings
from app.web import router as web_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """기동 시 누락된 테이블을 자동 생성하고 초기 관리자 계정을 만든다.

    create_all은 이미 존재하는 테이블을 건드리지 않으므로 운영에서도 안전하다.
    단, 기존 테이블의 컬럼 추가·변경은 직접 ALTER TABLE로 처리해야 한다.
    """
    from sqlalchemy import select

    from app.core.auth import hash_password
    from app.core.database import Base, SessionLocal, engine
    import app.models  # noqa: F401 - 모델 등록

    Base.metadata.create_all(engine)

    # 기존 users 테이블에 누락 컬럼 추가 (create_all은 컬럼 추가 안 함)
    from sqlalchemy import text
    _new_cols = [
        ("users", "display_name", "VARCHAR(128) DEFAULT ''"),
        ("users", "note", "TEXT"),
    ]
    with engine.connect() as _conn:
        for _tbl, _col, _typedef in _new_cols:
            try:
                _conn.execute(text(f"ALTER TABLE {_tbl} ADD COLUMN {_col} {_typedef}"))
                _conn.commit()
            except Exception:
                _conn.rollback()  # 이미 존재하면 무시

    # 초기 관리자 계정 — 존재하지 않을 때만 생성
    from app.models.user import User

    db = SessionLocal()
    try:
        if not db.scalar(select(User).where(User.username == "Administrator")):
            db.add(User(username="Administrator", hashed_password=hash_password("123qwer!")))
            db.commit()
    finally:
        db.close()

    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
)

# 세션 미들웨어 — 쿠키에 서명된 세션 데이터 저장 (7일 유지)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=86400 * 7,
    https_only=False,
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
