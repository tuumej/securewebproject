"""애플리케이션 설정. 모든 값은 환경변수(.env)에서 로드한다."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "securewebproject"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "change-me"

    # Infra
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/appdb"
    redis_url: str = "redis://localhost:6379/0"

    # Crawling
    crawl_user_agent: str = "securewebproject-bot/1.0"
    crawl_timeout_seconds: int = 15

    # 알림 (Slack)
    slack_webhook_url: str = ""

    # 알림 (Telegram)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 보안뉴스 수집 대상
    # 1) 데일리시큐 긴급속보
    news_dailysecu_url: str = (
        "https://www.dailysecu.com/news/articleList.html"
        "?sc_sub_section_code=S2N4&view_type=sm"
    )
    # 2) 보안뉴스(boannews) 사건·사고
    #    articleList.html?sc_section_code=S1N2 는 익명 요청 시 섹션 필터가 적용되지 않고
    #    전체 기사를 반환한다. 사건·사고만 얻으려면 섹션별 RSS 피드를 사용한다.
    news_boannews_url: str = (  # 사람이 보는 사건·사고 페이지 (설정 화면 링크용)
        "https://www.boannews.com/news/articleList.html"
        "?sc_section_code=S1N2&view_type=sm"
    )
    news_boannews_rss_url: str = "https://cdn.boannews.com/rss/gn_rss_S1N2.xml"
    # 3) KCERT(KNVD) 보안공지 — Vue SPA라 JSON API로 조회
    news_kcert_api_url: str = (
        "https://knvd.krcert.or.kr/api/core/pu/view/vuln-notice/get"
    )
    news_kcert_detail_url: str = "https://knvd.krcert.or.kr/info/vuln/notice/detail?id="

    news_slack_channel: str = "#security-news"

    # 하위호환: 기존 news_list_url 참조 코드를 위해 데일리시큐 URL을 별칭으로 제공
    @property
    def news_list_url(self) -> str:
        return self.news_dailysecu_url


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 로드해 캐싱한다."""
    return Settings()


settings = get_settings()
