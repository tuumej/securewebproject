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
| **진단** | Ubuntu 24.04 대상 서버에 SSH로 접속해 접속 확인 → 6단계 파이프라인으로 읽기 전용 취약점 점검을 수행. 판정 기준(YAML)과 수집 로직(코드)이 분리되어 있어 앱 안에서 기준을 직접 편집하고, 진단 실행마다 어떤 기준(KISA 등)을 적용할지 선택 가능 |
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
│  ├─ celery_app.py     # Celery 앱 + Beat 스케줄
│  └─ crypto.py         # 진단 SSH 자격증명 암호화(Fernet, SECRET_KEY 유도)
├─ models/              # SQLAlchemy 모델 (history, news, diagnosis)
├─ schemas/             # Pydantic 스키마
├─ services/
│  ├─ crawler.py        # 범용 페이지 크롤러
│  ├─ notifier.py       # Slack/이메일 알림 전송
│  ├─ security_news.py  # 3개 매체 수집·중복제거·알림
│  ├─ diagnosis_ssh.py        # SSH 접속(TOFU 호스트키 고정) + 접속 테스트
│  ├─ diagnosis_collectors.py # 수집기 5종 — "어떻게 값을 가져오는가"만 담은 코드
│  ├─ diagnosis_rules.py      # 진단 기준 YAML 로딩/검증/CRUD — "무엇을 기대하는가"는 데이터로만 존재
│  └─ diagnosis_engine.py     # 6단계 파이프라인 오케스트레이션(수집기 호출 + 기준 비교/판정)
├─ diagnosis_rules/     # 진단 기준 YAML (ruleset id = 파일명, 예: kisa_ubuntu.yaml)
├─ tasks/jobs.py        # Celery 태스크
├─ templates/           # Jinja2 템플릿 (대시보드/크롤링/보안뉴스/이력/진단/진단기준편집/알림/설정)
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
| `SECRET_KEY` | 세션 시크릿 겸 **진단 대상 SSH 자격증명 암호화 키의 원천**. 운영에서는 반드시 강력한 랜덤값으로 교체하세요. 이 값을 회전하면 이미 등록된 진단 대상의 자격증명은 복호화할 수 없어 재등록이 필요합니다. | `openssl rand -hex 32`로 생성 |

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
| POST | `/api/diagnosis/targets` | 진단 대상 서버 등록 (자격증명 암호화 저장) |
| GET | `/api/diagnosis/targets` | 진단 대상 목록 |
| DELETE | `/api/diagnosis/targets/{id}` | 진단 대상 삭제 |
| POST | `/api/diagnosis/targets/{id}/test-connection` | SSH 접속만 시도해보고 즉시 닫음(점검 실행 없음, 동기) |
| POST | `/api/diagnosis/targets/{id}/scan` | 진단 스캔 시작 (body `{ruleset_id}` 필수, 백그라운드 큐 등록) |
| GET | `/api/diagnosis/scans` | 최근 진단 스캔 목록 |
| GET | `/api/diagnosis/scans/{id}` | 진단 스캔 상세 + 점검 결과 (폴링용, `phase`/`os_id` 포함) |
| GET | `/api/diagnosis/scans/{id}/report` | 스캔 결과를 텍스트 리포트로 다운로드 |
| GET | `/api/diagnosis/rulesets` | 등록된 진단 기준(YAML) 목록 |
| GET | `/api/diagnosis/rulesets/{id}` | 진단 기준 상세 + 원본 YAML 텍스트 |
| POST | `/api/diagnosis/rulesets` | 새 진단 기준 생성 (빈 템플릿) |
| PUT | `/api/diagnosis/rulesets/{id}` | 진단 기준 YAML 검증 후 저장 (검증 실패 시 422 + 오류 목록) |
| DELETE | `/api/diagnosis/rulesets/{id}` | 진단 기준 삭제 |

## 🖥 화면 (상단 메뉴)

`Dashboard · 크롤링 · 보안뉴스 · 이력 · 진단 · 🔔 알림(미확인 배지) · ⚙ 설정(우측 끝)`

## 🔬 진단(Diagnosis) 기능 구조 — 규칙(YAML) ↔ 로직(코드) 분리

판정 기준을 코드에 하드코딩하지 않고, "어떻게 값을 가져오는가"(수집기)와
"무엇을 기대하는가"(규칙)를 분리했습니다.

- **수집기**(`app/services/diagnosis_collectors.py`, 코드) — SSH로 원시 데이터를
  가져오는 5종의 범용 함수: `sshd_config_value`, `systemd_service_active`,
  `command_value`, `command_list_lines`, `risky_ports`. 새 진단 항목은 대부분
  코드 수정 없이 YAML 규칙만 추가하면 됩니다.
- **규칙**(`app/diagnosis_rules/*.yaml`, 데이터) — 파일 하나가 하나의 진단
  기준(ruleset)이며 파일명(확장자 제외)이 ruleset id입니다. 항목마다
  `target`(`collector_id:파라미터`), `compare`(`equals_any`/`not_equals_any`/
  `list_empty`), `expected`, `severity`, `on_missing`, `needs_sudo`,
  `recommendation`을 정의합니다. 기본 제공: `kisa_ubuntu.yaml`(KISA 기준 발췌,
  U-01~U-13). ISMS-P/주요정보통신기반시설/자체 기준 등은 같은 스키마로 새
  파일을 추가하면 되고, **진단을 실행할 때마다 어떤 기준을 적용할지 선택**할 수
  있습니다.
- **엔진**(`app/services/diagnosis_engine.py`) — 아래 6단계를 순서대로 실행합니다.
  1. **SSH 접속 확인** — 실패 시 이후 단계로 진행하지 않고 스캔을 실패 처리
  2. **① OS 식별** — `/etc/os-release` 조회
  3. **② 진단 항목 수집** — 규칙별 `target`이 가리키는 수집기 실행
  4. **③ 기준값과 비교** — 수집된 값을 규칙의 `compare`/`expected`와 비교
  5. **④ 양호/취약 판정** — 비교 결과 + `on_missing` 규칙으로 pass/fail/unknown 결정
  6. **⑤ 증적 저장** — 수집기의 원시 출력을 finding의 `evidence`로 저장
  7. **⑥ 결과 리포트 생성** — 스캔 요약(심각도별 개수) + 다운로드 가능한 텍스트 리포트

기준을 앱 안에서 직접 조회/생성/편집/삭제할 수 있는 편집 UI(`/diagnosis/rules`)도
제공합니다.

## 🔒 진단(Diagnosis) 기능 보안 참고

- 대부분의 수집기는 **읽기 전용** 조회 명령만 사용합니다. 다만 `command_value`/
  `command_list_lines` 두 수집기는 YAML 규칙의 `target`에 적힌 **임의의 셸
  명령**을 그대로 SSH로 실행하는 범용 수집기입니다 — 규칙 편집 UI에 접근할 수
  있는 사람은 대상 서버에서 임의 명령을 실행시킬 수 있다는 뜻입니다. 이 앱은
  원래 별도 인증 체계가 없는 내부 도구이고(대상 서버 자격증명 자체도 이미 등록
  가능) 이는 기존 위협모델과 같은 수준이므로 별도의(뚫리기 쉬운) 명령 차단
  목록으로 막지 않고, 규칙 편집 화면에 경고 문구로 명시하는 방식을 택했습니다.
  진단 기준 편집 권한은 신뢰할 수 있는 운영자에게만 부여하세요.
- 호스트 키는 TOFU(최초 접속 시 지문 저장) 방식으로 고정됩니다. 이후 접속에서 호스트
  키가 달라지면 접속을 거부합니다(MITM/서버 교체 감지). 최초 접속 자체를
  out-of-band로 검증하지는 않으므로 완벽한 방어는 아닙니다.
- SSH 비밀번호/개인키는 `SECRET_KEY`에서 유도한 키로 암호화(Fernet)해 저장하며 평문으로
  보관하지 않습니다. 개인키는 **패스프레이즈 없는 키만** 지원합니다.
- 진단은 앱 → 대상 서버로 나가는 아웃바운드 SSH 연결만 사용하며, 새로운 인바운드
  공격면을 추가하지 않습니다.
- 대상 등록 후 "연결 테스트"로 SSH 접속 가능 여부만 먼저 확인할 수 있고, 진단
  실행 자체도 첫 단계에서 접속을 확인합니다(접속 실패 시 점검을 시도하지 않음).

## ✅ 테스트

```bash
pytest
```

---

## 📌 참고

- 각 매체의 "오늘자"는 게시 실제 현황에 따르며, 오늘자 기사가 없는 매체는 대시보드에 표시되지 않습니다.
- Slack Webhook 미설정 시 알림은 전송되지 않고 콘솔에 출력됩니다(개발 편의용 스텁).
