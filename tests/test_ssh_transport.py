from types import SimpleNamespace

import pytest

from runtime.cli import main
from runtime.errors import ProviderError
from runtime.hy3d_client import Hy3DClient
from runtime.ssh_transport import SshTunnel, check_remote, ssh_command, validate_ssh


def test_missing_server_fails_before_launch(monkeypatch):
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("Must not launch SSH"))
    with pytest.raises(ProviderError, match="not configured"):
        Hy3DClient({"type": "ssh", "ssh": {"host": None}})


@pytest.mark.parametrize("config", [
    {"host": "-oProxyCommand=bad"}, {"host": "host; touch bad"}, {"host": "server", "port": 0},
    {"host": "server", "user": "user@host"}, {"host": "server", "password": "not-allowed"},
    {"host": "server", "local_port": True}, {"host": "server", "connect_timeout_s": 3600},
])
def test_invalid_ssh_fields_rejected(config):
    with pytest.raises(ProviderError):
        validate_ssh(config)


def test_ssh_forwarding_is_loopback_and_host_keys_are_checked():
    command = ssh_command({"host": "gpu-alias", "user": "ubuntu", "port": 2202}, executable="ssh")
    assert command[-1] == "gpu-alias"
    assert "127.0.0.1:18080:127.0.0.1:8080" in command
    assert "StrictHostKeyChecking=yes" in command
    assert "BatchMode=yes" in command
    assert "ForwardAgent=no" in command
    assert "-N" in command


def test_identity_path_spaces_are_preserved(tmp_path):
    key = tmp_path / "key with spaces"
    key.write_text("test path only, not a real key")
    command = ssh_command({"host": "gpu", "identity_file": str(key)}, executable="ssh")
    assert command[command.index("-i") + 1] == str(key.resolve())


def test_ssh_endpoint_is_derived_and_not_spoofable():
    client = Hy3DClient({"type": "ssh", "ssh": {"host": "gpu", "local_port": 19080}}, transport=lambda *a: {})
    assert client.endpoint == "http://127.0.0.1:19080"
    assert client.kind == "ssh"
    with pytest.raises(ProviderError, match="derives endpoint"):
        Hy3DClient({"type": "ssh", "ssh": {"host": "gpu"}, "endpoint": "https://elsewhere.test"})


def test_remote_check_is_read_only_and_not_health_check():
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="Linux\nPython 3.10\nGPU, 49152 MiB, driver", stderr="")
    result = check_remote({"host": "gpu"}, runner=run)
    assert result["status"] == "ssh_connected"
    assert "nvidia-smi" in calls[0][-1]
    assert "-L" not in calls[0]
    assert "HY3D service" in result["note"]


def test_tunnel_does_not_reuse_an_unrelated_local_service(monkeypatch):
    monkeypatch.setattr(SshTunnel, "_port_open", lambda self: True)
    with pytest.raises(ProviderError, match="occupied"):
        with SshTunnel({"host": "gpu"}):
            pytest.fail("Must not enter an occupied tunnel")


def test_tunnel_closes_its_process_on_request_failure(monkeypatch):
    class Process:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, **kwargs):
            return 0
    process = Process()
    checks = iter([False, True])
    monkeypatch.setattr(SshTunnel, "_port_open", lambda self: next(checks))
    monkeypatch.setattr("runtime.ssh_transport.subprocess.Popen", lambda *a, **kw: process)
    with pytest.raises(RuntimeError):
        with SshTunnel({"host": "gpu"}):
            raise RuntimeError("inference failed")
    assert process.stopped


def test_client_wraps_http_in_ssh_and_closes_tunnel(monkeypatch):
    events = []
    class Tunnel:
        def __init__(self, config):
            assert config["host"] == "gpu"
        def __enter__(self):
            events.append("open")
        def __exit__(self, *args):
            events.append("close")
    monkeypatch.setattr("runtime.hy3d_client.SshTunnel", Tunnel)
    client = Hy3DClient({"type": "ssh", "ssh": {"host": "gpu"}})
    def request(*args):
        events.append("request")
        return {"status": "ok", "capabilities": []}
    monkeypatch.setattr(client, "_request", request)
    assert client.health_check()["status"] == "ok"
    assert events == ["open", "request", "close"]


def test_unconfigured_cli_gives_actionable_error(capsys):
    assert main(["ssh-check", "--config", "configs/hy3d_ssh.yaml"]) == 2
    assert "not configured" in capsys.readouterr().err
