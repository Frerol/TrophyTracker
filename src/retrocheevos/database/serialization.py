"""Conversions between Python values and their SQLite-storable representation."""

from datetime import datetime
from typing import Optional


def datetime_to_sql(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def datetime_from_sql(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value is not None else None
