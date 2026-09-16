import json
import re
import struct
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from runtime.errors import BoundaryError, ValidationError
from runtime.io import inside, load_data, sha256


CONTRACT_FORMATS = FormatChecker()


@CONTRACT_FORMATS.checks("date-time", raises=(ValueError, TypeError))
def valid_timestamp(value):
    # Do not depend on jsonschema's optional RFC3339 extra being installed.
    if not isinstance(value, str):
        return True  # The schema's type constraint handles non-strings.
    return (re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
                         r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})", value) is not None
            and datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00")).tzinfo is not None)


def validate_contract(name, value):
    if isinstance(value, dict) and (value.get("schema_version") == "0.2" or name == "visual_audit_bundle"):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Visual contracts require finite JSON values") from exc
    resources = {p.name: (Path(str(p)).resolve().as_uri(), json.loads(p.read_text(encoding="utf-8")))
                 for p in files("contracts").iterdir() if p.name.endswith(".schema.json")}
    registry = Registry().with_resources((uri, Resource.from_contents(schema)) for uri, schema in resources.values())
    if name + ".schema.json" not in resources:
        raise ValidationError(f"Unknown contract: {name}")
    uri, _ = resources[name + ".schema.json"]
    errors = sorted(Draft202012Validator({"$ref": uri}, registry=registry,
                    format_checker=CONTRACT_FORMATS).iter_errors(value),
                    key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise ValidationError(f"{name}:{'.'.join(map(str, error.path))}: {error.message}")
    return value


def validate_manifest(manifest):
    version = manifest.get("schema_version") if isinstance(manifest, dict) else None
    if version not in ("0.1", "0.2"):
        raise ValidationError(f"Unsupported manifest schema_version: {version}")
    validate_contract("project_manifest_v02" if version == "0.2" else "project_manifest", manifest)
    for asset_id, task in manifest["assets"].items():
        if task["asset_id"] != asset_id:
            raise ValidationError("Asset map key must match asset_id")
        result = task["result"]
        if result and (result["asset_id"] != asset_id or result["revision"] != task["revision"]):
            raise ValidationError("Result belongs to another asset or revision")
        if task["status"] in ("approved", "review_required") and result is None:
            raise ValidationError("Reviewable assets must have a validated result")
    if version == "0.2":
        from runtime.visual_contracts import validate_visual_manifest
        validate_visual_manifest(manifest)
    return manifest


def require_legacy_manifest(manifest):
    if manifest["schema_version"] != "0.1":
        raise BoundaryError("Legacy production execution is unavailable for schema 0.2; Phase 1 supports contracts only")


def validate_model(path):
    """Lightweight container validation, not topology or visual QA."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValidationError(f"Missing or empty model: {path}")
    try:
        if path.suffix.lower() == ".glb":
            with path.open("rb") as stream:
                magic, version, length = struct.unpack("<4sII", stream.read(12))
                if magic != b"glTF" or version != 2 or length != path.stat().st_size:
                    raise ValueError("invalid GLB header")
                size, kind = struct.unpack("<II", stream.read(8))
                if kind != 0x4E4F534A or size > length - 20 or size % 4:
                    raise ValueError("invalid JSON chunk")
                document = json.loads(stream.read(size))
                if not document.get("meshes") or document.get("asset", {}).get("version") != "2.0":
                    raise ValueError("GLB must contain a glTF 2.0 mesh")
                for item in document.get("buffers", []) + document.get("images", []):
                    if "uri" in item and not item["uri"].startswith("data:"):
                        raise ValueError("GLB resources must be embedded")
                while stream.tell() < length:
                    chunk_size, _ = struct.unpack("<II", stream.read(8))
                    if chunk_size % 4 or stream.tell() + chunk_size > length:
                        raise ValueError("invalid binary chunk")
                    stream.seek(chunk_size, 1)
        elif path.suffix.lower() == ".obj":
            lines = path.read_text(encoding="utf-8").splitlines()
            if any(line.strip().startswith("mtllib ") for line in lines):
                raise ValueError("MVP supports geometry-only OBJ; use embedded GLB for materials")
            if not any(x.startswith("v ") for x in lines) or not any(x.startswith("f ") for x in lines):
                raise ValueError("OBJ requires vertices and faces")
        else:
            raise ValueError("MVP import supports embedded GLB and geometry-only OBJ")
    except (ValueError, struct.error, UnicodeError, OSError) as exc:
        raise ValidationError(f"Invalid model {path}: {exc}") from exc
    return path


def validate_result(root, result):
    validate_contract("stage1_result", result)
    source = result["source"]
    if source["license"] == "cc_by" and not source["attribution_required"]:
        raise BoundaryError("CC BY assets must retain required attribution")
    from runtime.asset_router import AssetRouter
    if not AssetRouter().legal({"source": source}, generated_output=result["route"] == "hy3d_generate"):
        raise BoundaryError("Result has unverified or unsupported licensing")
    if result["route"] == "library_hy3d_refine" and not source["modification_allowed"]:
        raise BoundaryError("Refinement requires modification rights")
    prefix = f"stage1/outputs/{result['asset_id']}/rev{result['revision']:02d}/"
    if not result["files"]["model"].replace("\\", "/").startswith(prefix):
        raise BoundaryError("Worker result must stay inside its asset revision output directory")
    path = validate_model(inside(root, result["files"]["model"]))
    if sha256(path) != result["sha256"]:
        raise ValidationError("Asset checksum mismatch")
    return path


def stage2_preflight(root, manifest, plan):
    validate_manifest(manifest)
    require_legacy_manifest(manifest)
    validate_contract("blender_plan", plan)
    if manifest["mode"] not in ("stage2_only", "full_pipeline", "repair"):
        raise BoundaryError(f"Stage 2 prohibited in {manifest['mode']} mode")
    if not manifest["plan_approved"]:
        raise BoundaryError("The refined production plan must be approved first")
    if plan["style"]["style_bible"] != manifest["style_bible"]:
        raise BoundaryError("Blender plan must use the project's style bible")
    load_data(inside(root, manifest["style_bible"]))
    ids = [entry["asset_id"] for entry in plan["assets"]]
    if len(ids) != len(set(ids)):
        raise ValidationError("Duplicate asset placements; use procedural repetition in MVP")
    required = {k for k, t in manifest["assets"].items() if t["required"]}
    if manifest["mode"] == "stage2_only":
        required |= set(manifest["supplied_assets"])
    if not manifest["allow_partial"] and not required.issubset(ids):
        raise BoundaryError(f"Plan omits required assets: {sorted(required - set(ids))}")
    resolved = {}
    for asset_id in ids:
        if manifest["mode"] == "stage2_only" and asset_id in manifest["supplied_assets"]:
            entry = manifest["supplied_assets"][asset_id]
            from runtime.asset_router import AssetRouter
            if not AssetRouter().legal({"source": entry["source"]}, modification=True):
                raise BoundaryError("Supplied asset rights no longer permit Blender processing")
            path = validate_model(inside(root, entry["model"]))
            if sha256(path) != entry["sha256"]:
                raise ValidationError(f"Supplied asset changed: {asset_id}")
        else:
            task = manifest["assets"].get(asset_id)
            if not task or task["status"] != "approved":
                raise BoundaryError(f"Asset {asset_id} is not approved")
            path = validate_result(root, task["result"])
            if not task["result"]["source"]["modification_allowed"]:
                raise BoundaryError("Blender normalization requires modification rights")
        resolved[asset_id] = str(path)
    if not manifest["allow_partial"] and manifest["mode"] != "stage2_only":
        if any(manifest["assets"][k]["status"] != "approved" for k in required):
            raise BoundaryError("All required assets must be approved")
    return resolved
