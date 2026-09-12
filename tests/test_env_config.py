from argparse import Namespace

import pytest

from runtime.cli import execute
from runtime.errors import ValidationError
from runtime.io import load_data


def test_cli_loads_root_dotenv_and_process_environment_wins(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "HY3D_SSH_HOST=gpu.internal.example\n"
        "HY3D_SSH_PORT=2222\n"
        "HY3D_SSH_USER=render-user\n"
        "HY3D_API_TOKEN=file-secret\n",
        encoding="utf-8",
    )
    config = tmp_path / "hy3d.yaml"
    config.write_text(
        "type: ssh\n"
        "ssh:\n"
        "  host: ${HY3D_SSH_HOST}\n"
        "  port: ${HY3D_SSH_PORT}\n"
        "  user: ${HY3D_SSH_USER}\n"
        "token_env: HY3D_API_TOKEN\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("runtime.io.DEFAULT_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("HY3D_SSH_HOST", raising=False)
    monkeypatch.delenv("HY3D_SSH_PORT", raising=False)
    monkeypatch.delenv("HY3D_API_TOKEN", raising=False)
    monkeypatch.setenv("HY3D_SSH_USER", "process-user")
    captured = {}

    def fake_check_remote(ssh):
        captured.update(ssh)
        return {"status": "checked"}

    monkeypatch.setattr("runtime.ssh_transport.check_remote", fake_check_remote)
    result = execute(Namespace(command="ssh-check", config=str(config)))

    assert result == {"status": "checked"}
    assert captured == {"host": "gpu.internal.example", "port": 2222, "user": "process-user"}
    assert __import__("os").environ["HY3D_API_TOKEN"] == "file-secret"


def test_plain_yaml_without_placeholders_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr("runtime.io.DEFAULT_ENV_FILE", tmp_path / ".env")
    config = tmp_path / "local.yaml"
    config.write_text("type: local\nendpoint: http://127.0.0.1:8080\ntimeout_s: 300\n", encoding="utf-8")

    assert load_data(config) == {
        "type": "local",
        "endpoint": "http://127.0.0.1:8080",
        "timeout_s": 300,
    }


def test_absent_environment_placeholder_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("runtime.io.DEFAULT_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("HY3D_SSH_HOST", raising=False)
    config = tmp_path / "hy3d.yaml"
    config.write_text("type: ssh\nssh:\n  host: ${HY3D_SSH_HOST}\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="HY3D_SSH_HOST"):
        load_data(config)
