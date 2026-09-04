"""보안뉴스 API 스키마."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SecurityNewsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str = "dailysecu"
    idxno: str
    title: str
    url: str
    published_at: datetime | None = None
    is_read: bool
    is_archived: bool = False
    created_at: datetime


class UnreadCount(BaseModel):
    count: int


class RefreshResult(BaseModel):
    new_count: int
