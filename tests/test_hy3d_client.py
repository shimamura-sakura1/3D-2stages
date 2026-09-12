import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from runtime.errors import ProviderError, ValidationError
from runtime.hy3d_client import Hy3DClient


@pytest.mark.parametrize("kind,endpoint", [("local", "http://localhost:8080"), ("remote", "https://example.test")])
def test_backend_abstraction(kind, endpoint, tmp_path, glb_bytes):
    calls = []
    def transport(method, path, body):
        calls.append((method, path, body))
        if path == "/health":
            return {"status": "ok", "capabilities": ["generate_textured_asset"]}
        return {"model_base64": base64.b64encode(glb_bytes).decode()}
    client = Hy3DClient({"type": kind, "endpoint": endpoint}, transport)
    result = client.generate_textured_asset(prompt="bench", reference_images=[], output_dir=tmp_path, style_bible={})
    assert result.read_bytes() == glb_bytes
    assert calls[1][1] == "/v1/generate_textured_asset"
    assert calls[1][2]["prompt"] == "bench"


def test_health_failure_prevents_inference(tmp_path):
    calls = []
    def transport(method, path, body):
        calls.append(path)
        return {"status": "down", "capabilities": []}
    client = Hy3DClient({"type": "local", "endpoint": "http://localhost:8080"}, transport)
    with pytest.raises(ProviderError, match="health"):
        client.generate_shape(prompt="bench", reference_images=[], output_dir=tmp_path, style_bible={})
    assert calls == ["/health"]


def test_generation_failure(tmp_path):
    def transport(method, path, body):
        return {"status": "ok", "capabilities": ["generate_shape"]} if path == "/health" else {"error": "failure"}
    client = Hy3DClient({"type": "local", "endpoint": "http://localhost:8080"}, transport)
    with pytest.raises(ProviderError, match="generation failed"):
        client.generate_shape(prompt="bench", reference_images=[], output_dir=tmp_path, style_bible={})


def test_capability_mismatch(tmp_path):
    client = Hy3DClient({"type": "local", "endpoint": "http://localhost:8080"},
                       lambda *args: {"status": "ok", "capabilities": ["generate_shape"]})
    with pytest.raises(ProviderError, match="does not support"):
        client.retexture_mesh(prompt="bench", reference_images=[], output_dir=tmp_path, style_bible={})


@pytest.mark.parametrize("config", [
    {"type": "remote", "endpoint": "http://example.test"},
    {"type": "local", "endpoint": "http://someone.test"},
    {"type": "remote", "endpoint": "https://user:secret@example.test"},
    {"type": "remote", "endpoint": "https://example.test?token=secret"},
])
def test_unsafe_configuration_rejected(config):
    with pytest.raises(ProviderError):
        Hy3DClient(config)


def test_real_http_transport_against_loopback_gateway(tmp_path, glb_bytes, monkeypatch):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "capabilities": ["generate_shape"]}).encode())

        def do_POST(self):
            requests.append((self.path, self.headers.get("Authorization"),
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"model_base64": base64.b64encode(glb_bytes).decode()}).encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TEST_HY3D_TOKEN", "test-only-token")
    try:
        client = Hy3DClient({"type": "local", "endpoint": f"http://127.0.0.1:{server.server_port}",
                            "token_env": "TEST_HY3D_TOKEN"})
        path = client.generate_shape(prompt="bench", reference_images=[], output_dir=tmp_path, style_bible={})
        assert path.read_bytes() == glb_bytes
        assert requests[0][0] == "/v1/generate_shape"
        assert requests[0][1] == "Bearer test-only-token"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
