"""시각. DB 에는 UTC(시간대 정보 없는 값)로 저장하고, 작업 ID 날짜는 한국 시각으로 정한다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분하다


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def kst_date(utc_naive: datetime) -> str:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(KST).strftime("%Y%m%d")


def kst_day_start_utc(utc_naive: datetime) -> datetime:
    local = utc_naive.replace(tzinfo=timezone.utc).astimezone(KST)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
