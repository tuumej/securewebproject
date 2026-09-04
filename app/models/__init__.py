"""모델 패키지. Alembic autogenerate가 인식하도록 모든 모델을 import 한다."""
from app.models.diagnosis import DiagnosisFinding, DiagnosisScan, DiagnosisTarget
from app.models.history import CrawlRecord, NotificationLog
from app.models.news import SecurityNews
from app.models.notification_target import NotificationTarget
from app.models.settings import AppSetting
from app.models.user import User

__all__ = [
    "CrawlRecord",
    "NotificationLog",
    "SecurityNews",
    "DiagnosisTarget",
    "DiagnosisScan",
    "DiagnosisFinding",
    "AppSetting",
    "NotificationTarget",
    "User",
]
