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
