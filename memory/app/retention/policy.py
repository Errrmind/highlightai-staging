"""90-day retention policy."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import config


class RetentionPolicy:
    def __init__(self, days: int | None = None) -> None:
        self.days = days if days is not None else config.RETENTION_DAYS

    def expires_at(self, created: datetime | None = None) -> datetime:
        created = created or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created + timedelta(days=self.days)

    def is_expired(self, expires_at: datetime, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= expires_at

    def purge_expired(self, items: list[dict]) -> tuple[list[dict], list[dict]]:
        kept, purged = [], []
        for item in items:
            exp = item.get("expires_at")
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp is None or not self.is_expired(exp):
                kept.append(item)
            else:
                purged.append(item)
        return kept, purged
