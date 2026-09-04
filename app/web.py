"""HTML 페이지 라우터 — 상단 메뉴별 기능 페이지를 렌더링한다."""
from pathlib import Path

import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(include_in_schema=False)


def _ctx(request: Request, extra: dict | None = None) -> dict:
    """공통 템플릿 컨텍스트 — 세션 유효성 검사 후 로그인 사용자명을 포함한다."""
    from app.core.auth import check_session
    ctx: dict = {"current_user": check_session(request)}
    if extra:
        ctx.update(extra)
    return ctx


# ── 공개 페이지 ─────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", _ctx(request, {"active": "dashboard"}))


@router.get("/crawl", response_class=HTMLResponse)
def crawl_page(request: Request):
    return templates.TemplateResponse(request, "crawl.html", _ctx(request, {"active": "crawl"}))


@router.get("/notify", response_class=HTMLResponse)
def notify_page(request: Request):
    return templates.TemplateResponse(request, "notify.html", _ctx(request, {"active": "notify"}))


@router.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return templates.TemplateResponse(request, "history.html", _ctx(request, {"active": "history"}))


@router.get("/diagnosis", response_class=HTMLResponse)
def diagnosis_page(request: Request):
    return templates.TemplateResponse(request, "diagnosis.html", _ctx(request, {"active": "diagnosis"}))


@router.get("/diagnosis/rules", response_class=HTMLResponse)
def diagnosis_rules_page(request: Request):
    return templates.TemplateResponse(request, "diagnosis_rules.html", _ctx(request, {"active": "diagnosis"}))


@router.get("/security-news", response_class=HTMLResponse)
def security_news_page(request: Request):
    return templates.TemplateResponse(request, "security_news.html", _ctx(request, {"active": "security-news"}))


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request):
    return templates.TemplateResponse(request, "alerts.html", _ctx(request, {"active": "alerts"}))


# ── 로그인 전용 페이지 ──────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    from app.core.auth import check_session
    if not check_session(request):
        return RedirectResponse("/login?next=/settings", status_code=302)
    ctx = _ctx(request, {
        "active": "settings",
        "slack_configured": bool(settings.slack_webhook_url),
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "telegram_chat_id": settings.telegram_chat_id,
        "news_dailysecu_url": settings.news_dailysecu_url,
        "news_boannews_url": settings.news_boannews_url,
        "news_slack_channel": settings.news_slack_channel,
    })
    return templates.TemplateResponse(request, "settings.html", ctx)


# ── 로그인 / 로그아웃 ───────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("username"):
        return RedirectResponse("/settings", status_code=302)
    next_url = request.query_params.get("next", "/settings")
    return templates.TemplateResponse(request, "login.html", {"current_user": None, "next": next_url, "error": None})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/settings"),
):
    from sqlalchemy import select

    from app.core.auth import verify_password
    from app.core.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == username))
        if user and verify_password(password, user.hashed_password):
            request.session["username"] = username
            request.session["last_activity"] = time.time()
            return RedirectResponse(next or "/settings", status_code=302)
    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "login.html",
        {"current_user": None, "next": next, "error": "아이디 또는 비밀번호가 틀렸습니다."},
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
