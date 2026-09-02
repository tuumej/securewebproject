# syntax=docker/dockerfile:1
FROM python:3.13-slim

# 보안: root가 아닌 사용자로 실행
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# 기본 커맨드는 web 서버. worker/beat는 docker-compose에서 override.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
