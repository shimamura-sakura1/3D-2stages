"""Real CLI/file/loopback HTTP lifecycle; this is not remote GPU evidence."""
import base64
import copy
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from runtime.cli import main
from runtime.io import atomic_write, load_data, sha256
from runtime.planning import new_task

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def gateway(glb, capabilities):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(("GET", self.path, None))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "capabilities": capabilities}).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, body))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"model_base64": base64.b64encode(glb).decode()}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def cli(capsys, *args, expected=0):
    assert main([str(arg) for arg in args]) == expected
    captured = capsys.readouterr()
    return json.loads(captured.out if expected == 0 else captured.err)


def setup_case(tmp_path, candidate, endpoint, route):
    candidate = copy.deepcopy(candidate)
    if route == "B":
        candidate["scores"]["style_fit"] = 0.2
    library = tmp_path / "library"
    library.mkdir()
    (library / "bench.obj").write_bytes((ROOT / "examples/library/bench.obj").read_bytes())
    catalog = library / "catalog.yaml"
    atomic_write(catalog, {"assets": [] if route == "C" else [candidate]})
    config = tmp_path / "gateway.yaml"
    # The loopback server returns the locally authored triangle fixture.
    source = {**candidate["source"], "provider": "fixture_gateway", "asset_id": "original_triangle",
              "creator": "Two-Stage 3D test fixture", "original_url": "local:tests/conftest.py#glb_bytes"}
    atomic_write(config, {"type": "local", "endpoint": endpoint, "output_source": source})
    return catalog, config


@pytest.mark.parametrize("route,operation,expected_route", [
    ("A", None, "library_direct"),
    ("B", "retexture_mesh", "library_hy3d_refine"),
    ("C", "generate_textured_asset", "hy3d_generate"),
    ("C", "generate_shape", "hy3d_generate"),
])
def test_positive_complete_stage1_lifecycle(tmp_path, candidate, glb_bytes, capsys, route, operation, expected_route):
    with gateway(glb_bytes, ["retexture_mesh", "generate_textured_asset", "generate_shape"]) as (endpoint, calls):
        catalog, config = setup_case(tmp_path, candidate, endpoint, route)
        root = tmp_path / "project"
        task = new_task("bench")
        task["review"]["max_revisions"] = 1
        if operation == "generate_shape":
            task["hy3d"]["mode"] = "shape"
        task_path = tmp_path / "task.yaml"
        atomic_write(task_path, task)
        cli(capsys, "init", root, "--id", "stage1_test", "--brief", "bench", "--mode", "stage1_only", "--task", task_path)
        cli(capsys, "approve-plan", root)
        args = ("run", root, "--asset-id", "bench", "--catalog", catalog, "--hy3d-config", config)
        assert cli(capsys, *args)["status"] == "stage1_checkpoint"
        manifest = cli(capsys, "status", root)
        asset = manifest["assets"]["bench"]
        assert asset["status"] == "review_required"
        assert asset["result"]["route"] == expected_route
        first = root / asset["result"]["files"]["model"]
        original_hash = sha256(first)
        assert asset["result"]["sha256"] == original_hash
        assert manifest["stage2"]["status"] == "not_started"
        cli(capsys, "configure", root, "--target", "asset")
        assert "approved" in cli(capsys, "deliver", root, expected=2)["error"]
        cli(capsys, "review", root, "bench", "--decision", "revision_requested", "--instruction", "Use a cleaner silhouette")
        assert cli(capsys, *args)["status"] == "stage1_checkpoint"
        revised = cli(capsys, "status", root)["assets"]["bench"]
        assert revised["revision"] == 1 and revised["status"] == "review_required"
        assert sha256(first) == original_hash
        assert revised["result"]["files"]["model"] != asset["result"]["files"]["model"]
        if operation:
            posts = [entry for entry in calls if entry[0] == "POST"]
            assert len(posts) == 2
            assert all(entry[1] == "/v1/" + operation for entry in posts)
            assert "Use a cleaner silhouette" in posts[-1][2]["prompt"]
            assert posts[-1][2]["seed"] == 1
            if route == "B":
                assert base64.b64decode(posts[0][2]["mesh"]["data_base64"]) == (ROOT / "examples/library/bench.obj").read_bytes()
        else:
            assert calls == []
        cli(capsys, "review", root, "bench", "--decision", "approved")
        delivery = cli(capsys, "deliver", root)
        assert delivery["target"] == "asset"
        assert sha256(root / delivery["files"][0]) == revised["result"]["sha256"]
        assert delivery["attribution"] == [revised["result"]["source"]]
        package = (root / delivery["files"][0]).parent
        assert (package / "checksums.json").is_file()
        assert (package / "manifest.snapshot.yaml").is_file()
        assert cli(capsys, "status", root)["state"] == "complete"
        cli(capsys, "review", root, "bench", "--decision", "revision_requested", "--instruction", "Another revision")
        before = (root / "manifest.yaml").read_bytes()
        call_count = len(calls)
        assert "revision" in cli(capsys, *args, expected=2)["error"].lower()
        assert (root / "manifest.yaml").read_bytes() == before
        assert len(calls) == call_count
        assert sha256(first) == original_hash


@pytest.mark.parametrize("failure", ["provider", "rights", "capability"])
def test_rejection_before_generation_and_no_automatic_failed_retry(tmp_path, candidate, glb_bytes, capsys, failure):
    with gateway(glb_bytes, []) as (endpoint, calls):
        catalog, config = setup_case(tmp_path, candidate, endpoint, "C")
        if failure == "rights":
            document = load_data(config)
            document.pop("output_source")
            atomic_write(config, document)
        root = tmp_path / "project"
        cli(capsys, "init", root, "--id", "rejection", "--brief", "bench", "--mode", "stage1_only", "--asset", "bench")
        cli(capsys, "approve-plan", root)
        args = ["run", root, "--asset-id", "bench", "--hy3d-config", config]
        if failure != "provider":
            args.extend(["--catalog", catalog])
        message = cli(capsys, *args, expected=2)["error"]
        assert {"provider": "Provider not configured", "rights": "output rights", "capability": "does not support"}[failure] in message
        assert not [entry for entry in calls if entry[0] == "POST"]
        if failure != "capability":
            assert calls == []
        before = (root / "manifest.yaml").read_bytes()
        assert cli(capsys, "run", root)["status"] == "stage1_checkpoint"
        assert (root / "manifest.yaml").read_bytes() == before
        assert cli(capsys, "status", root)["assets"]["bench"]["status"] == "failed"
