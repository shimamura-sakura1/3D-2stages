"""Client for our explicit HY3D gateway protocol, not a presumed upstream API."""
import base64
import http.client
import json
import os
from contextlib import contextmanager, nullcontext
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from runtime.errors import ProviderError
from runtime.validators import validate_model
from runtime.ssh_transport import SshTunnel, validate_ssh


# Static codes verified in the deployed gateway protocol; never echo arbitrary tokens.
SAFE_GATEWAY_ERROR_CODES = frozenset({'invalid_request', 'unsupported_conditioning',
                                      'invalid_seed', 'unexpected_mesh'})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("HY3D gateway redirects are disabled")


class Hy3DClient:
    def __init__(self, config, transport=None):
        self.config = config
        self.kind = config.get("type")
        self.endpoint = config.get("endpoint", "").rstrip("/")
        self.ssh_config = None
        if self.kind == "ssh":
            self.ssh_config = validate_ssh(config.get("ssh"))
            expected = f"http://127.0.0.1:{self.ssh_config['local_port']}"
            if self.endpoint and self.endpoint != expected:
                raise ProviderError("SSH mode derives endpoint from ssh.local_port; remove endpoint")
            self.endpoint = expected
        parsed = urllib.parse.urlsplit(self.endpoint)
        if self.kind not in ("local", "remote", "ssh") or parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ProviderError("Configure a local, remote HTTPS, or SSH HY3D gateway")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError("Endpoint must not contain credentials, query strings, or fragments")
        if self.kind == "remote" and parsed.scheme != "https":
            raise ProviderError("Remote HY3D endpoints must use HTTPS")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ProviderError("Plain HTTP is restricted to a local gateway")
        self.transport = transport or self._http
        self._scoped_capabilities = None

    def _http(self, method, path, body):
        with SshTunnel(self.ssh_config) if self.ssh_config else nullcontext():
            return self._request(method, path, body)

    def _request(self, method, path, body):
        token_env = self.config.get("token_env")
        headers = {"Content-Type": "application/json"}
        if token_env:
            token = os.environ.get(token_env)
            if not token:
                raise ProviderError(f"Missing credential environment variable: {token_env}")
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.endpoint + path,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers=headers, method=method)
        try:
            handlers = [NoRedirect]
            if urllib.parse.urlsplit(self.endpoint).hostname in ("localhost", "127.0.0.1", "::1"):
                handlers.append(urllib.request.ProxyHandler({}))
            with urllib.request.build_opener(*handlers).open(request, timeout=self.config.get("timeout_s", 300)) as response:
                data = response.read(256 * 1024 * 1024 + 1)
                if len(data) > 256 * 1024 * 1024:
                    raise ProviderError("Gateway response exceeds 256 MiB")
                return json.loads(data)
        except urllib.error.HTTPError as exc:
            detail = f'HTTP {exc.code}'
            try:
                raw = exc.read(8193)
                if len(raw) <= 8192:
                    payload = json.loads(raw)
                    error = payload.get('error') if isinstance(payload, dict) else None
                    code = error.get('code') if isinstance(error, dict) else None
                    if isinstance(code, str) and code in SAFE_GATEWAY_ERROR_CODES:
                        detail += f'; code={code}'
            except (OSError, ValueError, RecursionError, http.client.HTTPException):
                pass
            finally:
                exc.close()
            raise ProviderError(f'HY3D gateway {method} {path} failed ({detail})') from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # Do not include headers, service response bodies, or secrets in logs.
            raise ProviderError(f"HY3D gateway {method} {path} failed ({type(exc).__name__})") from None

    def health_check(self):
        try:
            data = self.transport("GET", "/health", None)
            if not isinstance(data, dict) or data.get("status") != "ok" or not isinstance(data.get("capabilities"), list):
                raise ProviderError("HY3D health check failed or gateway protocol unsupported")
            return data
        except (OSError, ValueError) as exc:
            raise ProviderError("HY3D health check failed") from exc

    @contextmanager
    def operation_scope(self, required_operations):
        """Preflight one acquisition's operations together before spending inference."""
        capabilities = self.health_check()['capabilities']
        for operation in required_operations:
            if operation not in capabilities:
                raise ProviderError(f'Gateway does not support {operation}')
        previous = self._scoped_capabilities
        self._scoped_capabilities = capabilities
        try:
            yield
        finally:
            self._scoped_capabilities = previous

    def _run(self, operation, *, prompt, reference_images, output_dir, style_bible, mesh=None, seed=0):
        capabilities = self._scoped_capabilities if self._scoped_capabilities is not None else self.health_check()['capabilities']
        if operation not in capabilities:
            raise ProviderError(f"Gateway does not support {operation}")
        def encode(path):
            path = Path(path)
            if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
                raise ProviderError("Input missing or exceeds 64 MiB")
            return {"name": path.name, "data_base64": base64.b64encode(path.read_bytes()).decode()}
        payload = {"prompt": prompt, "reference_images": [encode(p) for p in reference_images],
                   "style_bible": style_bible, "seed": seed}
        if mesh:
            payload["mesh"] = encode(mesh)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "asset.glb"
        if target.exists():
            raise ProviderError("Generation output already exists; start a new revision")
        try:
            data = self.transport("POST", f"/v1/{operation}", payload)
            model = base64.b64decode(data["model_base64"], validate=True)
            with target.open("xb") as stream:
                stream.write(model)
            validate_model(target)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise ProviderError(f"HY3D generation failed ({type(exc).__name__})") from None
        return target

    def generate_shape(self, **kwargs):
        return self._run("generate_shape", **kwargs)

    def generate_geometry(self, **kwargs):
        """Semantic geometry entry point over the existing gateway operation."""
        try:
            return self.generate_shape(**kwargs)
        except (AttributeError, TypeError) as exc:
            raise ProviderError('Invalid geometry generation model structure') from exc

    def generate_surface_source(self, *, mesh=None, **kwargs):
        """Retexture an explicit mesh; preserve this raw result as reference evidence."""
        from runtime.hy3d_surface import validate_surface_source
        if mesh is None or not Path(mesh).is_file():
            raise ProviderError('Surface generation requires an existing input mesh')
        try:
            validate_model(mesh)
            result = self.retexture_mesh(mesh=mesh, **kwargs)
        except (AttributeError, TypeError) as exc:
            raise ProviderError('Invalid surface generation model structure') from exc
        return validate_surface_source(result)

    def generate_textured_asset(self, **kwargs):
        return self._run("generate_textured_asset", **kwargs)

    def retexture_mesh(self, **kwargs):
        return self._run("retexture_mesh", **kwargs)
