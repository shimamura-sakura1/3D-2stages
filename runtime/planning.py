import copy
from importlib.resources import files

from runtime.io import atomic_write, inside, load_data
from runtime.manifest_manager import ManifestManager
from runtime.validators import validate_contract


def visual_manifest(project_id, brief):
    """Construct an unapproved visual plan; does not execute any Stage 0–3 work."""
    return {"schema_version": "0.2", "project_id": project_id, "version": 0,
            "mode": "plan_only", "user_brief": {"raw": brief, "refined": brief},
            "assets": {}, "supplied_assets": {}, "auto_approve": False, "allow_partial": False,
            "history": [], "state": "initialized", "scene_version": 1, "artifacts": {},
            "approvals": [], "legacy_manifest": None, "migration_required_input": []}


def create_visual_project(root, project_id, brief):
    manager = ManifestManager(root)
    manager.create(visual_manifest(project_id, brief))
    inside(root, "user_brief.md").write_text(brief + "\n", encoding="utf-8")
    return manager.read()


def new_task(asset_id, description=None):
    task = load_data(files("templates").joinpath("asset_task.yaml"))
    task.update(asset_id=asset_id, name=asset_id)
    task["target"]["scale_hint"] = {}
    task["target"]["description"] = description or asset_id.replace("_", " ")
    task["search"]["keywords"] = [task["target"]["description"]]
    return validate_contract("asset_task", task)


def create_project(root, project_id, brief, mode="plan_only", tasks=(), refined=None):
    manifest = copy.deepcopy(load_data(files("templates").joinpath("project_manifest.yaml")))
    manifest.update(project_id=project_id, mode=mode,
                    user_brief={"raw": brief, "refined": refined or brief})
    for task in tasks:
        validate_contract("asset_task", task)
        if task["asset_id"] in manifest["assets"] or task["status"] != "planned" or task["revision"] != 0:
            raise ValueError("Initial tasks must be unique, planned, and at revision zero")
        manifest["assets"][task["asset_id"]] = task
    manifest["groups"] = sorted({task["group_id"] for task in tasks})
    manager = ManifestManager(root)
    manager.create(manifest)
    for directory in ("planning", "stage1/tasks", "stage1/candidates", "stage1/sources", "stage1/outputs",
                      "stage1/results", "stage1/reviews", "stage2/scene", "stage2/reviews", "delivery/outputs"):
        inside(root, directory).mkdir(parents=True, exist_ok=True)
    inside(root, "user_brief.md").write_text(brief + "\n", encoding="utf-8")
    atomic_write(inside(root, "style_bible.yaml"), load_data(files("templates").joinpath("style_bible.yaml")))
    for task in tasks:
        atomic_write(inside(root, f"stage1/tasks/{task['asset_id']}.yaml"), task)
    return manager.read()
