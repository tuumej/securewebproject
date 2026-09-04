"""보안뉴스 크롤링 및 갱신 로직 (다중 출처).

수집 대상
- dailysecu : 데일리시큐 긴급속보        (articlek CMS, HTML 파싱)
- boannews  : 보안뉴스 사건·사고          (articlek CMS, HTML 파싱 — dailysecu와 동일 구조)
- kcert     : KCERT(KNVD) 보안공지        (Vue SPA → JSON API)

- fetch_*(): 각 출처 목록을 [{source, idxno, title, url, published_at}] 로 반환
- refresh_security_news(db): 출처별 신규 기사만 저장, 오늘자 신규는 Slack 알림
"""
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.news import SecurityNews
from app.services.notifier import send_to_all_enabled

KST = timezone(timedelta(hours=9))

# 출처 코드 → 사람이 읽는 이름 (Slack 메시지/화면 라벨)
SOURCE_LABELS = {
    "dailysecu": "데일리시큐 긴급속보",
    "boannews": "보안뉴스 사건·사고",
    "kcert": "KCERT 보안공지",
}

_IDXNO_RE = re.compile(r"idxno=(\d+)")
_DATE_RE = re.compile(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2})")


def _parse_published(info_text: str) -> datetime | None:
    """'... 09-01 08:04' 형태에서 게시 일시(KST)를 파싱한다. 연도는 현재 연도로 가정."""
    m = _DATE_RE.search(info_text or "")
    if not m:
        return None
    month, day, hour, minute = (int(x) for x in m.groups())
    now = datetime.now(KST)
    try:
        dt = datetime(now.year, month, day, hour, minute, tzinfo=KST)
    except ValueError:
        return None
    # 연말/연초 경계 보정: 파싱값이 미래로 크게 벌어지면 작년 기사로 처리
    if dt - now > timedelta(days=1):
        dt = dt.replace(year=now.year - 1)
    return dt


def _date_from_objectid(oid: str) -> datetime | None:
    """MongoDB ObjectId 앞 4바이트(생성 시각)를 KST datetime으로 변환한다."""
    if not oid or len(oid) < 8:
        return None
    try:
        ts = int(oid[:8], 16)
    except ValueError:
        return None
    return datetime.fromtimestamp(ts, KST)


def _http_get(url: str) -> httpx.Response:
    resp = httpx.get(
        url,
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp


def _fetch_articlek_cms(url: str, source: str, limit: int) -> list[dict]:
    """articlek CMS(데일리시큐/보안뉴스) 목록 페이지를 파싱한다.

    두 사이트는 동일 CMS라 selector가 같다: li.altlist-webzine-item.
    """
    soup = BeautifulSoup(_http_get(url).text, "html.parser")

    items: list[dict] = []
    seen: set[str] = set()
    for li in soup.select("li.altlist-webzine-item"):
        a = li.select_one("h2.altlist-subject a[href*='articleView.html']")
        if not a:
            continue
        href = a.get("href", "")
        m = _IDXNO_RE.search(href)
        if not m:
            continue
        idxno = m.group(1)
        if idxno in seen:
            continue
        seen.add(idxno)

        title = a.get_text(strip=True)
        info = li.select_one(".altlist-info")
        published_at = _parse_published(info.get_text(" ", strip=True) if info else "")

        items.append(
            {
                "source": source,
                "idxno": idxno,
                "title": title,
                "url": href,
                "published_at": published_at,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_dailysecu(limit: int = 30) -> list[dict]:
    """데일리시큐 긴급속보 목록."""
    return _fetch_articlek_cms(settings.news_dailysecu_url, "dailysecu", limit)


def fetch_boannews(limit: int = 30) -> list[dict]:
    """보안뉴스 사건·사고 목록.

    boannews의 articleList.html은 익명 요청 시 sc_section_code 필터를 무시하고 전체
    기사를 반환한다. 따라서 사건·사고만 정확히 얻기 위해 섹션 RSS 피드를 파싱한다.
    """
    resp = _http_get(settings.news_boannews_rss_url)
    root = ET.fromstring(resp.content)

    items: list[dict] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        m = _IDXNO_RE.search(link)
        if not m or not title:
            continue
        idxno = m.group(1)
        if idxno in seen:
            continue
        seen.add(idxno)

        published_at = None
        pub = item.findtext("pubDate")
        if pub:
            try:
                published_at = parsedate_to_datetime(pub).astimezone(KST)
            except (TypeError, ValueError):
                published_at = None

        items.append(
            {
                "source": "boannews",
                "idxno": idxno,
                "title": title,
                "url": link,
                "published_at": published_at,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_kcert(limit: int = 30) -> list[dict]:
    """KCERT(KNVD) 보안공지 목록. Vue SPA라 JSON API로 조회한다."""
    payload = {
        "sortBy": "_id",
        "order": -1,
        "skipCount": 0,
        "limit": limit,
        "preKey": "",
        "nextKey": "",
        "changePerpage": False,
        "collectionType": "VULNOTICE",
        "searchOption": "KEYWORD",
        "content": "",
    }
    resp = httpx.post(
        settings.news_kcert_api_url,
        json=payload,
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("resType") != "RES_OK":
        return []

    items: list[dict] = []
    for row in data.get("resList") or []:
        oid = row.get("id") or ""
        # 안정적 중복키: 게시글 번호(idx) 우선, 없으면 ObjectId 사용
        idxno = str(row.get("idx") or oid)
        title = (row.get("title") or "").strip()
        if not idxno or not title:
            continue
        items.append(
            {
                "source": "kcert",
                "idxno": idxno,
                "title": title,
                "url": f"{settings.news_kcert_detail_url}{oid}",
                "published_at": _date_from_objectid(oid),
            }
        )
        if len(items) >= limit:
            break
    return items


# 갱신 시 순회할 출처 페처
_FETCHERS = (fetch_dailysecu, fetch_boannews, fetch_kcert)


def fetch_all_news(limit: int = 30) -> list[dict]:
    """모든 출처를 수집한다. 한 출처가 실패해도 나머지는 계속 진행한다."""
    out: list[dict] = []
    for fetch in _FETCHERS:
        try:
            out.extend(fetch(limit))
        except Exception:  # noqa: BLE001 - 개별 출처 장애 격리
            continue
    return out


def is_today_kst(dt: datetime | None) -> bool:
    """게시 일시가 오늘(KST)인지 판정한다."""
    if dt is None:
        return False
    return dt.astimezone(KST).date() == datetime.now(KST).date()


def refresh_security_news(db: Session) -> list[SecurityNews]:
    """모든 출처의 보안 기사를 갱신한다. 신규만 저장하고 오늘자 신규는 Slack 알림.

    반환값: 이번에 새로 저장된 SecurityNews 목록.
    """
    fetched = fetch_all_news()
    if not fetched:
        return []

    # 출처별 기존 idxno 집합을 미리 조회해 중복을 거른다.
    by_source: dict[str, list[dict]] = {}
    for it in fetched:
        by_source.setdefault(it["source"], []).append(it)

    existing: dict[str, set[str]] = {}
    for source, items in by_source.items():
        idxnos = [it["idxno"] for it in items]
        existing[source] = set(
            db.scalars(
                select(SecurityNews.idxno).where(
                    SecurityNews.source == source,
                    SecurityNews.idxno.in_(idxnos),
                )
            )
        )

    new_items: list[SecurityNews] = []
    for it in fetched:
        if it["idxno"] in existing.get(it["source"], set()):
            continue
        news = SecurityNews(
            source=it["source"],
            idxno=it["idxno"],
            title=it["title"],
            url=it["url"],
            published_at=it["published_at"],
            is_read=False,
        )
        db.add(news)
        new_items.append(news)

    if not new_items:
        return []

    db.commit()

    # 오늘자 신규 기사만 알림 전송 (과거 기사 대량 알림 방지)
    for news in new_items:
        if not is_today_kst(news.published_at):
            continue
        label = SOURCE_LABELS.get(news.source, news.source)
        msg = f"[{label}] {news.title}\n{news.url}"
        try:
            send_to_all_enabled(msg)
        except Exception:  # noqa: BLE001
            pass

    return new_items
