"""웹 크롤링 로직. httpx로 페이지를 가져와 제목/본문을 추출한다."""
import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


def fetch_page(url: str) -> dict[str, str]:
    """주어진 URL을 크롤링해 title과 text를 반환한다.

    실패 시 httpx 예외를 그대로 올린다(호출부에서 이력에 기록).
    """
    headers = {"User-Agent": settings.crawl_user_agent}
    resp = httpx.get(
        url,
        headers=headers,
        timeout=settings.crawl_timeout_seconds,
        follow_redirects=True,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    # 스크립트/스타일 제거 후 본문 텍스트만
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())

    return {"title": title, "content": text[:5000]}
