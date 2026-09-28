import httpx
import pytest

from app.dam_source.models import FetchError, InvalidQuarterError, Quarter
from app.dam_source.source import OreeDamSource
from tests.fakes import HEADER_ONLY, csv_bytes


class Transport:
    """Підставний транспорт: відповідає зі списку кроків і рахує звернення."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx.Response(status, content=body)


def make_source(transport: Transport, sleeps: list | None = None) -> OreeDamSource:
    async def fake_sleep(seconds):
        if sleeps is not None:
            sleeps.append(seconds)

    return OreeDamSource(transport=httpx.MockTransport(transport), sleep=fake_sleep)


def timeout():
    return httpx.ReadTimeout("timeout")


async def test_url_and_timeout():
    t = Transport((200, HEADER_ONLY))
    source = make_source(t)
    await source.fetch_quarter(2026, 3)
    assert str(t.requests[0].url) == (
        "https://www.oree.com.ua/index.php/control/results_mo_stat_csv/DAM/2026/3"
    )
    assert source.timeout == 30.0


async def test_retries_after_timeout_then_succeeds():
    body = csv_bytes("01.07.2026;1;100.00;1.0;1.0;1.0;1.0")
    t = Transport(timeout(), (200, body))
    sleeps = []
    fetch = await make_source(t, sleeps).fetch_quarter(2026, 3)
    assert len(fetch.records) == 1
    assert len(t.requests) == 2
    assert sleeps == [1.0]


async def test_retries_on_5xx():
    t = Transport((503, b""), (200, HEADER_ONLY))
    await make_source(t).fetch_quarter(2026, 3)
    assert len(t.requests) == 2


async def test_no_retry_on_4xx():
    t = Transport((404, b""))
    with pytest.raises(FetchError):
        await make_source(t).fetch_quarter(2026, 3)
    assert len(t.requests) == 1


async def test_gives_up_after_three_attempts_with_distinct_error():
    t = Transport(timeout())
    sleeps = []
    with pytest.raises(FetchError) as exc:
        await make_source(t, sleeps).fetch_quarter(2026, 3)
    assert not isinstance(exc.value, InvalidQuarterError)
    assert len(t.requests) == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize("quarter", [0, 5])
async def test_invalid_quarter_rejected_before_network(quarter):
    t = Transport((200, HEADER_ONLY))
    with pytest.raises(InvalidQuarterError):
        await make_source(t).fetch_quarter(2026, quarter)
    assert t.requests == []


async def test_empty_quarter_fixture_is_empty_result_not_error(fixture_bytes):
    t = Transport((200, fixture_bytes("dam_2019_Q2.csv")))
    fetch = await make_source(t).fetch_quarter(2019, 2)
    assert fetch.records == ()
    assert fetch.quarter == Quarter(2019, 2)


async def test_status_code_is_not_used_to_detect_data():
    # ОРЕЕ віддає 200 і для порожнього кварталу — наявність визначають лише рядки.
    t = Transport((200, HEADER_ONLY))
    fetch = await make_source(t).fetch_quarter(2030, 1)
    assert fetch.records == ()
