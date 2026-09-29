import json
import subprocess

from tests.conftest import ROOT, postgres_env_file


def compose_config() -> dict:
    out = subprocess.run(
        ["docker", "compose", "--env-file", str(postgres_env_file()), "config", "--format", "json"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return json.loads(out.stdout)


def test_every_published_port_is_loopback_only():
    services = compose_config()["services"]
    assert {"postgres", "backend", "web"} <= services.keys()
    published = [(name, p) for name, svc in services.items() for p in svc.get("ports", [])]
    assert published, "стек мусить публікувати хоча б UI"
    for name, port in published:
        assert port.get("host_ip") == "127.0.0.1", (name, port)


def test_backend_talks_to_the_compose_database():
    backend = compose_config()["services"]["backend"]
    assert backend["environment"]["DATABASE_URL"].endswith("@postgres:5432/dam")
    assert backend["depends_on"]["postgres"]["condition"] == "service_healthy"
