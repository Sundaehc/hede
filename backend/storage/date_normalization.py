from __future__ import annotations

import re
from datetime import date, datetime


DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}")
MONTH_DAY_RE = re.compile(r"^\d{1,2}\.\d{1,2}$")


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    if DATE_RE.match(text):
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
    if DATETIME_RE.match(text):
        return parse_datetime(text).date() if parse_datetime(text) else None
    return None


def parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    if not DATETIME_RE.match(text):
        return None
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_date_range(value: object) -> tuple[date | None, date | None]:
    text = str(value).strip() if value is not None else ""
    if "~" not in text:
        parsed = parse_date(text)
        return parsed, parsed
    start_raw, end_raw = (part.strip() for part in text.split("~", 1))
    return parse_date(start_raw), parse_date(end_raw)


def parse_month_day(value: object, *, year: int | None = None) -> date | None:
    text = str(value).strip() if value is not None else ""
    if not text or not MONTH_DAY_RE.match(text):
        return None
    month_raw, day_raw = text.split(".", 1)
    try:
        return date(year or date.today().year, int(month_raw), int(day_raw))
    except ValueError:
        return None
