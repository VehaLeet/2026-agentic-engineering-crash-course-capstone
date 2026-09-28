from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")


def kyiv_today(now: datetime | None = None) -> date:
    """Сьогоднішня дата за Києвом, а не за годинником хоста (контейнер зазвичай в UTC)."""
    return (now or datetime.now(timezone.utc)).astimezone(KYIV).date()
