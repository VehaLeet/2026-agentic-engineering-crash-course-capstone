import pytest

from app.api import __main__ as launcher
from tests.conftest import ROOT


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
def test_loopback_hosts_accepted(host):
    assert launcher.resolve_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "example.com"])
def test_non_loopback_hosts_rejected(host):
    with pytest.raises(launcher.ConfigError, match=host.replace(".", r"\.")):
        launcher.resolve_host(host)


@pytest.fixture
def runs(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.uvicorn, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)
    return calls


def test_defaults_to_loopback_single_worker(runs):
    assert launcher.main() == 0
    [(args, kw)] = runs
    assert args == ("app.api.main:app",)
    assert kw == {"host": "127.0.0.1", "port": 8000, "workers": 1}


def test_env_overrides(runs, monkeypatch):
    monkeypatch.setenv("API_HOST", "::1")
    monkeypatch.setenv("API_PORT", "8123")
    launcher.main()
    assert runs[0][1]["host"] == "::1" and runs[0][1]["port"] == 8123


def test_refuses_to_open_to_network(runs, monkeypatch, capsys):
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    assert launcher.main() != 0
    assert runs == []  # сокет не відкривається
    assert "0.0.0.0" in capsys.readouterr().err


def test_env_example_has_no_credentials_and_documents_host():
    text = (ROOT / ".env.example").read_text()
    assert "API_USERNAME" not in text and "API_PASSWORD" not in text
    assert "# API_HOST=127.0.0.1" in text


# Режим контейнера

def test_container_mode_allows_any_address_inside_container(tmp_path):
    marker = tmp_path / ".dockerenv"
    marker.touch()
    assert launcher.resolve_host("0.0.0.0", container_mode=True, markers=[marker]) == "0.0.0.0"
    assert launcher.resolve_host("127.0.0.1", container_mode=True, markers=[marker]) == "127.0.0.1"


def test_container_mode_still_rejects_interface_addresses(tmp_path):
    marker = tmp_path / ".dockerenv"
    marker.touch()
    with pytest.raises(launcher.ConfigError, match=r"192\.168\.1\.10"):
        launcher.resolve_host("192.168.1.10", container_mode=True, markers=[marker])


def test_container_mode_outside_container_is_refused(tmp_path):
    with pytest.raises(launcher.ConfigError, match="лише всередині контейнера"):
        launcher.resolve_host("0.0.0.0", container_mode=True, markers=[tmp_path / "missing"])


def test_launcher_refuses_container_flag_on_host(runs, monkeypatch, capsys):
    monkeypatch.setattr(launcher, "CONTAINER_MARKERS", ())
    monkeypatch.setenv("API_IN_CONTAINER", "1")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    assert launcher.main() == 2
    assert runs == []
    assert "лише всередині контейнера" in capsys.readouterr().err
