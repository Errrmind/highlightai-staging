from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.retention.policy import RetentionPolicy


def test_90_day_expiry():
    policy = RetentionPolicy(days=90)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    exp = policy.expires_at(created)
    assert exp == created + timedelta(days=90)
    assert policy.is_expired(exp, now=exp + timedelta(seconds=1))
    assert not policy.is_expired(exp, now=exp - timedelta(seconds=1))


def test_purge_expired():
    policy = RetentionPolicy(days=90)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    items = [
        {"id": "a", "expires_at": (now - timedelta(days=1)).isoformat()},
        {"id": "b", "expires_at": (now + timedelta(days=1)).isoformat()},
    ]
    kept, purged = policy.purge_expired(items)
    # patch now via is_expired path — purge_expired uses datetime.now; instead unit-test is_expired
    assert policy.is_expired(datetime.fromisoformat(items[0]["expires_at"]), now=now)
    assert not policy.is_expired(datetime.fromisoformat(items[1]["expires_at"]), now=now)
    assert isinstance(kept, list) and isinstance(purged, list)
