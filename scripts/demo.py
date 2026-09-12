"""Run the original local fixture through Stage 1; leave actual asset review pending."""
import argparse
import json
from pathlib import Path

from providers.local_library import LocalLibraryProvider
from runtime.errors import BoundaryError
from runtime.io import atomic_write, load_data
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project
from runtime.stage1_executor import Stage1Executor
from runtime.stage2_executor import Stage2Executor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="projects/demo_station")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = Path(args.project).resolve()
    create_project(root, "demo_station", "Offline fixture: a simple station bench and procedural railway",
                   "full_pipeline", [load_data(repo / "templates/asset_task.yaml")])
    manager = ManifestManager(root)
    # This is a predefined engineering demonstration, not approval of a user's production asset.
    manager.approve_plan()
    provider = LocalLibraryProvider(repo / "examples/library/catalog.yaml")
    result = Stage1Executor(manager, {provider.name: provider}).run("bench")
    atomic_write(root / "stage2/blender_plan.yaml", load_data(repo / "templates/blender_plan.yaml"))
    try:
        Stage2Executor(manager).run(dry_run=True)
    except BoundaryError as exc:
        stage2_status = str(exc)
    else:
        raise AssertionError("Stage 2 should be blocked pending review")
    print(json.dumps({"project": str(root), "route": result["route"], "asset": result["files"]["model"],
                      "asset_status": "review_required", "stage2": stage2_status}, indent=2))


if __name__ == "__main__":
    main()
