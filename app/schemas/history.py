"""API 입출력 스키마 (Pydantic)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl


class CrawlRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    status: str
    title: str | None = None
    error: str | None = None
    created_at: datetime


class NotificationRequest(BaseModel):
    channel: str
    target: str
    message: str


class NotificationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel: str
    target: str
    status: str
    created_at: datetime
