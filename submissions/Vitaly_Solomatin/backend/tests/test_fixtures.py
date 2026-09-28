import pytest

from tests.conftest import FIXTURES

BOM = b"\xef\xbb\xbf"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.csv")), ids=lambda p: p.name)
def test_fixture_is_raw_oree_format(path):
    raw = path.read_bytes()
    assert raw.startswith(BOM)
    header, sep, _ = raw.partition(b"\r\n")
    assert sep == b"\r\n"
    assert len(header[len(BOM):].decode("utf-8").split(";")) == 7


def test_all_four_fixtures_present():
    assert len(list(FIXTURES.glob("*.csv"))) == 4
