"""OpenSSH transport for a loopback-only HY3D service on a remote GPU host."""
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from runtime.errors import ProviderError


def validate_ssh(config):
    if not isinstance(config, dict):
        raise ProviderError("Configure an ssh mapping before connecting")
    allowed = {"host", "port", "user", "identity_file", "known_hosts_file", "local_port", "remote_port", "connect_timeout_s"}
    if set(config) - allowed:
        raise ProviderError("Unsupported SSH fields; passwords and private key contents must not be stored in configuration")
    host = config.get("host")
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", host):
        raise ProviderError("SSH server is not configured: set ssh.host to a hostname, IP, or SSH alias")
    value = {"port": 22, "local_port": 18080, "remote_port": 8080, "connect_timeout_s": 10, **config}
    for field in ("port", "local_port", "remote_port"):
        if type(value[field]) is not int or not 1 <= value[field] <= 65535:
            raise ProviderError(f"ssh.{field} must be an integer in 1..65535")
    if type(value["connect_timeout_s"]) is not int or not 1 <= value["connect_timeout_s"] <= 30:
        raise ProviderError("ssh.connect_timeout_s must be an integer in 1..30")
    user = value.get("user")
    if user is not None and (not isinstance(user, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", user)):
        raise ProviderError("Invalid SSH username")
    for key in ("identity_file", "known_hosts_file"):
        if value.get(key) is not None:
            if not isinstance(value[key], str) or any(c in value[key] for c in "\r\n\0"):
                raise ProviderError(f"Invalid ssh.{key}")
            path = Path(value[key]).expanduser().resolve()
            if not path.is_file():
                raise ProviderError(f"ssh.{key} file does not exist: {path}")
            value[key] = str(path)
    return value


def ssh_command(config, *, tunnel=True, executable=None):
    config = validate_ssh(config)
    executable = executable or shutil.which("ssh")
    if not executable:
        raise ProviderError("OpenSSH client is not installed")
    command = [executable, "-T", "-p", str(config["port"]),
               "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ForwardAgent=no", "-o", "ControlMaster=no", "-o", "ControlPath=none",
               "-o", "RemoteCommand=none", "-o", f"ConnectTimeout={config['connect_timeout_s']}",
               "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]
    if config.get("user"):
        command += ["-l", config["user"]]
    if config.get("identity_file"):
        command += ["-i", config["identity_file"], "-o", "IdentitiesOnly=yes"]
    if config.get("known_hosts_file"):
        # This option's value has its own whitespace parser inside OpenSSH.
        path = config["known_hosts_file"].replace("\\", "/").replace('"', '\\"')
        command += ["-o", f'UserKnownHostsFile="{path}"']
    if tunnel:
        command += ["-N", "-o", "ExitOnForwardFailure=yes", "-L",
                    f"127.0.0.1:{config['local_port']}:127.0.0.1:{config['remote_port']}"]
    command += [config["host"]]
    return command


class SshTunnel:
    def __init__(self, config):
        self.config = validate_ssh(config)
        self.process = None
        self.log = None

    def _port_open(self):
        try:
            with socket.create_connection(("127.0.0.1", self.config["local_port"]), timeout=0.2):
                return True
        except OSError:
            return False

    def __enter__(self):
        if self._port_open():
            raise ProviderError("SSH local port is already occupied; choose another local_port")
        self.log = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        try:
            self.process = subprocess.Popen(ssh_command(self.config), stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=self.log,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + self.config["connect_timeout_s"] + 3
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    self.log.seek(0)
                    detail = self.log.read(2000).strip()
                    raise ProviderError(f"SSH connection failed: {detail or 'process exited'}. "
                                        "Check the host key and SSH key/agent; no inference was started.")
                if self._port_open():
                    return self
                time.sleep(0.1)
            raise ProviderError("SSH tunnel startup timed out; no inference was started")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.log:
            self.log.close()


def check_remote(config, runner=None):
    """Read-only diagnostics. No model download, package install, or remote writes."""
    config = validate_ssh(config)
    command = ssh_command(config, tunnel=False)
    command.append("uname -s; python3 --version; "
                   "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    try:
        result = (runner or subprocess.run)(command, stdin=subprocess.DEVNULL, capture_output=True,
                                             text=True, timeout=config["connect_timeout_s"] + 20,
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProviderError(f"SSH diagnostics failed: {type(exc).__name__}") from exc
    if result.returncode:
        raise ProviderError(f"SSH or GPU diagnostics failed: {result.stderr.strip()[:2000]}")
    return {"status": "ssh_connected", "environment": result.stdout.strip(),
            "note": "SSH/GPU check only; HY3D service readiness is a separate health check"}
