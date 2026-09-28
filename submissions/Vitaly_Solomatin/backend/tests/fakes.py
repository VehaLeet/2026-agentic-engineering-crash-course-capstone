from app.dam_source.models import Quarter
from app.dam_source.source import DamSource
from tests.conftest import FIXTURES

HEADER_ONLY = (FIXTURES / "dam_2019_Q2.csv").read_bytes()
HEADER = HEADER_ONLY.rstrip(b"\r\n")


def csv_bytes(*rows: str) -> bytes:
    """Синтетичний CSV у форматі ОРЕЕ: BOM-заголовок з фікстури + рядки через CRLF."""
    return HEADER + b"".join(b"\r\n" + r.encode() for r in rows) + b"\r\n"


class FakeDamSource(DamSource):
    """Джерело без мережі: квартал -> байти; відсутній квартал віддається як порожній."""

    def __init__(self, files: dict[Quarter, bytes] | None = None):
        self.files = dict(files or {})
        self.calls: list[Quarter] = []

    async def fetch_raw(self, quarter: Quarter) -> bytes:
        self.calls.append(quarter)
        return self.files.get(quarter, HEADER_ONLY)
