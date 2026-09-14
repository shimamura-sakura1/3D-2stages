"""Run one real image-to-shape request through the configured HY3D client."""
import argparse
import hashlib
import json
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.env_config import load_dotenv, resolve_environment
from runtime.hy3d_client import Hy3DClient
from runtime.io import load_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/hy3d_ssh.yaml")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    reference = Path(args.reference).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "operation": "generate_shape",
        "seed": 42,
        "reference": str(reference),
        "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
    }
    started = time.monotonic()
    try:
        client = Hy3DClient(resolve_environment(load_data(args.config)))
        report["health"] = client.health_check()
        print(json.dumps({"health": report["health"]}, ensure_ascii=False), flush=True)
        inference_started = time.monotonic()
        model = client.generate_shape(
            prompt="", reference_images=[reference], output_dir=output,
            style_bible={}, seed=42,
        )
        report["generation_request_seconds"] = round(time.monotonic() - inference_started, 2)
        data = model.read_bytes()
        json_size = struct.unpack_from("<I", data, 12)[0]
        document = json.loads(data[20:20 + json_size])
        report.update({
            "status": "passed", "model": str(model), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "mesh_count": len(document["meshes"]), "glb_validation": "passed",
        })
    except Exception as exc:
        # Avoid printing response bodies, credentials, or arbitrary exception text.
        report.update({"status": "failed", "error_type": type(exc).__name__})
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
