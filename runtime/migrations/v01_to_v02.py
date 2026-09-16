"""Safely map known v0.1 fields into a non-installable v0.2 draft."""
import copy

from runtime.planning import visual_manifest
from runtime.validators import validate_contract, validate_manifest


def plan_migration(legacy):
    validate_contract("project_manifest", legacy)
    validate_manifest(legacy)
    candidate = visual_manifest(legacy["project_id"], legacy["user_brief"]["raw"])
    candidate["user_brief"] = copy.deepcopy(legacy["user_brief"])
    candidate["assets"] = copy.deepcopy(legacy["assets"])
    candidate["supplied_assets"] = copy.deepcopy(legacy["supplied_assets"])
    # Prior approvals and delivery/history remain evidence for the old project only.
    candidate["legacy_manifest"] = copy.deepcopy(legacy)
    missing = ["visual_brief", "reference_board", "scene_spec", "style_assignment"]
    candidate["migration_required_input"] = list(missing)
    validate_manifest(candidate)
    return {"status": "migration_required_input", "required_inputs": missing,
            "candidate_manifest": candidate, "source_modified": False,
            "note": "Read-only draft. Source files remain in their original project; no migrated project is installed."}
