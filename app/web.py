"""HTML 페이지 라우터 — 상단 메뉴별 기능 페이지를 렌더링한다."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"active": "dashboard"})


@router.get("/crawl", response_class=HTMLResponse)
def crawl_page(request: Request):
    return templates.TemplateResponse(request, "crawl.html", {"active": "crawl"})


@router.get("/notify", response_class=HTMLResponse)
def notify_page(request: Request):
    return templates.TemplateResponse(request, "notify.html", {"active": "notify"})


@router.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return templates.TemplateResponse(request, "history.html", {"active": "history"})


@router.get("/security-news", response_class=HTMLResponse)
def security_news_page(request: Request):
    return templates.TemplateResponse(
        request, "security_news.html", {"active": "security-news"}
    )


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request):
    return templates.TemplateResponse(request, "alerts.html", {"active": "alerts"})


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    ctx = {
        "active": "settings",
        "slack_configured": bool(settings.slack_webhook_url),
        "news_dailysecu_url": settings.news_dailysecu_url,
        "news_boannews_url": settings.news_boannews_url,
        "news_slack_channel": settings.news_slack_channel,
    }
    return templates.TemplateResponse(request, "settings.html", ctx)
