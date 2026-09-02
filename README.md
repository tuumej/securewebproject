# securewebproject

> 웹 크롤링 · 보안뉴스 수집 · 알림 전송 · 이력관리 기능을 갖춘 보안 관제 웹 애플리케이션

FastAPI 기반의 웹 애플리케이션으로, 여러 보안 매체의 기사를 주기적으로 수집하고
새 기사가 올라오면 Slack으로 알림을 보냅니다. 다크 터미널풍 UI에서 크롤링·알림·이력을
통합 관리합니다.

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **대시보드** | 오늘자 보안뉴스 최신 3건, 크롤링/알림 통계, 시스템 상태 |
| **웹 크롤링** | 임의 URL을 큐에 등록해 백그라운드로 페이지 수집 (제목/본문 저장) |
| **보안뉴스 수집** | 3개 매체의 기사를 1시간 주기로 자동 수집 (아래 참고) |
| **알림 전송** | 신규 기사 발생 시 Slack Webhook으로 알림, 종(🔔) 배지에 미확인 수 표시 |
| **이력 관리** | 크롤링·알림 실행 기록 조회 |
| **설정** | 연동 상태(Slack), 수집 소스, 수동 갱신 |

### 수집 대상 (보안뉴스)

| 출처 | 대상 | 수집 방식 |
|------|------|-----------|
| **데일리시큐** | 긴급속보 | HTML 파싱 (`sc_sub_section_code=S2N4`) |
| **보안뉴스(boannews)** | 사건·사고 | **섹션 RSS 피드**(`gn_rss_S1N2.xml`) — articleList는 익명 요청 시 섹션 필터가 무시되어 전체 기사가 나오므로 RSS 사용 |
| **KCERT(KNVD)** | 보안공지 | **JSON API**(`/api/core/pu/view/vuln-notice/get`) — Vue SPA라 HTML에 기사가 없어 백엔드 API 호출, 게시일은 MongoDB ObjectId에서 디코딩 |

> 출처별로 idxno가 겹칠 수 있어 `(source, idxno)` 복합 유니크로 중복을 관리합니다.

---

## 🧱 기술 스택

- **FastAPI** — 웹 API + Jinja2 서버사이드 템플릿
- **Celery + Redis** — 백그라운드 작업 큐 & 1시간 주기 스케줄(Celery Beat)
- **PostgreSQL + SQLAlchemy 2.0 + Alembic** — 이력 저장 & 마이그레이션
- **httpx + BeautifulSoup** — 크롤링/파싱
- **Docker / docker-compose** — 배포
- 로컬 개발 시 **SQLite** 지원 (별도 DB 없이 즉시 실행)

## 🏗 아키텍처

```
사용자 ─HTTP→ FastAPI ─큐→ Redis ─→ Celery Worker ─→ 크롤링 / 알림 / 뉴스 수집
                 └────────────────→ DB (PostgreSQL / SQLite) : 이력·기사 저장
           Celery Beat ─(1시간 주기)→ Worker ─→ 신규 기사 수집 + Slack 알림
```

## 📁 프로젝트 구조

```
app/
├─ main.py              # FastAPI 진입점 (lifespan에서 SQLite 테이블 자동 생성)
├─ web.py               # HTML 페이지 라우터
├─ api/routes.py        # JSON API (크롤링/알림/뉴스/알림배지)
├─ core/
│  ├─ config.py         # 환경설정 (.env 로드)
│  ├─ database.py       # SQLAlchemy 엔진/세션/Base
│  └─ celery_app.py     # Celery 앱 + Beat 스케줄
├─ models/              # SQLAlchemy 모델 (history, news)
├─ schemas/             # Pydantic 스키마
├─ services/
│  ├─ crawler.py        # 범용 페이지 크롤러
│  ├─ notifier.py       # Slack/이메일 알림 전송
│  └─ security_news.py  # 3개 매체 수집·중복제거·알림
├─ tasks/jobs.py        # Celery 태스크
├─ templates/           # Jinja2 템플릿 (대시보드/크롤링/보안뉴스/이력/알림/설정)
└─ static/css/          # 다크 테마 스타일
alembic/                # DB 마이그레이션
tests/                  # pytest
Dockerfile · docker-compose.yml · requirements.txt
```

---

## 🚀 로컬 개발 (Docker 없이, SQLite)

`.env`의 `DATABASE_URL`이 SQLite면 서버 시작 시 테이블이 자동 생성되어 별도 DB 없이 바로 실행됩니다.

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
# (PowerShell에서 스크립트 실행이 막히면 .venv\Scripts\python.exe 를 직접 실행하세요)
pip install -r requirements.txt
cp .env.example .env               # DATABASE_URL=sqlite:///./dev.db 로 두면 즉시 실행

.venv/Scripts/python.exe -m uvicorn app.main:app --reload   # http://localhost:8000
```

- 크롤링/알림 큐 등록(`/api/crawl`, `/api/notify`)은 Redis + Celery 워커가 필요합니다.
- **보안뉴스 갱신**(`/api/security-news/refresh`)은 동기 처리라 Redis 없이도 동작합니다.
- 1시간 주기 자동 갱신 + Slack 알림은 워커/비트가 떠 있을 때 동작:
  ```bash
  celery -A app.core.celery_app.celery_app worker --loglevel=info   # 별도 터미널
  celery -A app.core.celery_app.celery_app beat --loglevel=info     # 별도 터미널
  ```

> 운영(PostgreSQL)에서는 자동 생성 대신 Alembic 마이그레이션을 사용하세요:
> `alembic revision --autogenerate -m "init" && alembic upgrade head`

## 🐳 Docker로 전체 실행

```bash
cp .env.example .env
docker compose up --build
docker compose exec web alembic upgrade head   # 최초 1회 마이그레이션
```

## ⚙️ 환경 변수 (.env)

| 변수 | 설명 | 예시 |
|------|------|------|
| `DATABASE_URL` | DB 접속 문자열 | `sqlite:///./dev.db` 또는 `postgresql+psycopg://user:pw@host:5432/db` |
| `REDIS_URL` | Celery 브로커 | `redis://localhost:6379/0` |
| `SLACK_WEBHOOK_URL` | Slack 알림 Webhook (비우면 알림은 콘솔 출력 스텁) | `https://hooks.slack.com/services/...` |
| `ENVIRONMENT` | 실행 환경 표시 | `development` |

`.env`는 커밋하지 않습니다(`.gitignore` 처리). 예시는 `.env.example` 참고.

---

## 📡 주요 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/health` | 헬스체크 |
| GET | `/docs` | Swagger 문서 |
| POST | `/api/crawl` | 크롤링 작업 등록 |
| POST | `/api/notify` | 알림 전송 작업 등록 |
| GET | `/api/history/crawls` | 크롤링 이력 |
| GET | `/api/history/notifications` | 알림 이력 |
| GET | `/api/security-news` | 보안뉴스 목록 (`today_only`, `auto_refresh`, `fallback_recent` 지원) |
| POST | `/api/security-news/refresh` | 보안뉴스 즉시 갱신(동기) |
| GET | `/api/alerts` | 알림 목록 |
| GET | `/api/alerts/unread-count` | 미확인 알림 수(종 배지) |
| POST | `/api/alerts/read` | 알림 모두 읽음 처리 |

## 🖥 화면 (상단 메뉴)

`Dashboard · 크롤링 · 보안뉴스 · 이력 · 🔔 알림(미확인 배지) · ⚙ 설정(우측 끝)`

## ✅ 테스트

```bash
pytest
```

---

## 📌 참고

- 각 매체의 "오늘자"는 게시 실제 현황에 따르며, 오늘자 기사가 없는 매체는 대시보드에 표시되지 않습니다.
- Slack Webhook 미설정 시 알림은 전송되지 않고 콘솔에 출력됩니다(개발 편의용 스텁).
