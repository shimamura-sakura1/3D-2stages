"""Deterministic visual document consistency checks, without production execution."""
import hashlib
import json

from runtime.errors import ValidationError


VISUAL_KINDS = ("visual_brief", "reference_board", "scene_spec", "style_assignment",
                "blockout_plan", "lookdev_plan", "render_plan", "semantic_material_map",
                "visual_review", "revision_plan", "render_metadata")


def document_hash(value):
    """SHA256 of UTF-8, sorted compact JSON; independent of YAML/JSON whitespace."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def unique(items, key, label):
    values = [item[key] for item in items]
    require(len(values) == len(set(values)), f"Duplicate {label}")
    return {item[key]: item for item in items}


def validate_visual_manifest(manifest):
    """Validate represented approval evidence, never create it from technical success."""
    from runtime.validators import validate_manifest
    if manifest["legacy_manifest"] is not None:
        validate_manifest(manifest["legacy_manifest"])
    current = manifest["scene_version"]
    latest = {}
    paths = set()
    for kind, records in manifest["artifacts"].items():
        pairs = [(r["document_id"], r["revision"]) for r in records]
        require(len(pairs) == len(set(pairs)), f"Duplicate {kind} document revision")
        for record in records:
            require(record["scene_version"] <= current, "Artifact refers to a future scene version")
            require(record["path"] not in paths, "Artifact revisions must use distinct paths")
            paths.add(record["path"])
        eligible = [r for r in records if r["scene_version"] == current]
        if eligible:
            latest[kind] = max(eligible, key=lambda r: r["revision"])["sha256"]
    for key in ('completion_evidence', 'final_reviews'):
        entries = manifest.get(key, [])
        require(len({r['path'] for r in entries}) == len(entries), 'Duplicate immutable evidence path')
        for record in entries:
            require(record['scene_version'] <= current and record['path'] not in paths,
                    'Invalid immutable evidence scene or reused artifact path')
            paths.add(record['path'])
    entries = manifest.get('completion_evidence', [])
    require(len({(r['scene_version'], r['pass_id']) for r in entries}) == len(entries), 'Duplicate completion pass evidence')
    deliveries = manifest.get('deliveries', [])
    require(len({r['package'] for r in deliveries}) == len(deliveries), 'Duplicate delivery package')
    require(all(r['scene_version'] <= current for r in deliveries), 'Future delivery scene')
    for approval in manifest["approvals"]:
        require(approval["scene_version"] <= current, "Approval refers to a future scene version")
    for asset_id, entry in manifest.get('geometry_assets', {}).items():
        versions = entry['versions']
        require(all(r['asset_id'] == asset_id and r['revision'] == i and r['scene_version'] <= current for i, r in enumerate(versions)), 'Geometry identity/revision mismatch')
    state = manifest["state"]
    if manifest["migration_required_input"]:
        require(state == "initialized", "Missing migration input cannot advance the scene")
    visual_states = {"visual_approved", "geometry_pending", "geometry_review_required",
                     "geometry_approved", "blockout_pending", "lookdev_pending", "render_pending",
                     "render_review_required", "visual_revision", "final_review_required", "approved", "delivered"}
    geometry_states = visual_states - {"visual_approved", "geometry_pending", "geometry_review_required"}
    required = []
    if state in visual_states:
        required.append(("visual", ("visual_brief", "reference_board", "scene_spec", "style_assignment")))
    if state in geometry_states:
        required.append(("geometry", ("scene_spec",)))
        require(all(t["status"] == "approved" for t in manifest["assets"].values() if t["required"]),
                "Required geometry assets must remain approved")
    if state in {"approved", "delivered"}:
        required.append(("final", ("render_plan", "render_metadata", "visual_review")))
    for scope, kinds in required:
        require(all(k in latest for k in kinds), f"Missing current {scope} artifacts")
        candidates = [a for a in manifest["approvals"] if a["scope"] == scope and a["scene_version"] == current]
        require(bool(candidates) and candidates[-1]["decision"] == "approved", f"Missing current {scope} user approval")
        expected = {latest[k] for k in kinds}
        if scope == "geometry":
            expected.update(t["result"]["sha256"] for t in manifest["assets"].values()
                            if t["required"] and t["result"])
            expected.update(a["sha256"] for a in manifest["supplied_assets"].values())
        if scope == 'geometry' and 'geometry_assets' in manifest:
            require(all(a['status'] == 'approved' for a in manifest['geometry_assets'].values()), 'Geometry must remain approved')
            expected.update(document_hash(a['versions'][-1]) for a in manifest['geometry_assets'].values())
        require(expected.issubset(candidates[-1]["artifact_hashes"]), f"Stale {scope} approval hashes")


def validate_visual_bundle(bundle):
    from runtime.state_machine import check_scene_transition
    from runtime.validators import validate_contract, validate_manifest
    validate_contract("visual_audit_bundle", bundle)
    docs = bundle["documents"]
    manifest = docs["project_manifest_v02"]
    validate_manifest(manifest)
    identities = [(docs[k]["project_id"], docs[k]["scene_version"]) for k in VISUAL_KINDS]
    require(all(pair == (manifest["project_id"], manifest["scene_version"]) for pair in identities),
            "Documents must share project_id and scene_version")
    for kind, records in manifest["artifacts"].items():
        current = [r for r in records if r["scene_version"] == manifest["scene_version"]]
        if current:
            record = max(current, key=lambda r: r["revision"])
            document = docs[kind]
            require(record["document_id"] == document["document_id"]
                    and record["revision"] == document["revision"]
                    and record["sha256"] == document_hash(document),
                    "Manifest artifact index does not match the audited document")
    unique([docs[k] for k in VISUAL_KINDS], "document_id", "document_id")
    refs = unique(docs["reference_board"]["references"], "reference_id", "reference_id")
    style = docs["style_assignment"]
    unique(style["references"], "reference_id", "style reference")
    for assignment in style["references"]:
        key = assignment["reference_id"]
        require(key in refs, "Unknown assigned reference")
        require(set(assignment["roles"]).issubset(refs[key]["roles"]), "Assigned reference role exceeds declared roles")
    scene = docs["scene_spec"]
    objects = unique(scene["objects"], "object_id", "scene object")
    require(scene["composition"]["focal_subject"] in objects, "Unknown focal subject")
    for item in objects.values():
        require(item["depth_layer"] in scene["composition"]["depth_layers"], "Undeclared depth layer")
        for relationship in item["relationships"]:
            require(relationship["object_id"] in objects and relationship["object_id"] != item["object_id"],
                    "Unknown or self scene relationship")
    placements = unique(docs["blockout_plan"]["objects"], "object_id", "blockout object")
    require(set(placements) == set(objects), "Blockout must describe every scene object exactly once")
    for item in placements.values():
        require(item["geometry_source"] == "procedural" or item["asset_id"] is not None,
                "Non-procedural placement requires an asset_id")
        seen = {item["object_id"]}
        parent = item["parent"]
        while parent is not None:
            require(parent in placements and parent not in seen, "Unknown or cyclic blockout parent")
            seen.add(parent)
            parent = placements[parent]["parent"]
    material = docs["semantic_material_map"]
    slots = set()
    for entry in material["mappings"]:
        require(entry["object_id"] in placements, "Unknown material object")
        pair = entry["object_id"], entry["slot"]
        require(pair not in slots, "Duplicate semantic material slot")
        slots.add(pair)
    lookdev = docs["lookdev_plan"]
    require(lookdev["style_assignment_id"] == style["document_id"], "Unknown lookdev style assignment")
    require(lookdev["material_map_id"] == material["document_id"], "Unknown lookdev material map")
    require(lookdev["lighting"]["profile"] == style["lighting_profile"], "Lighting profile mismatch")
    require(lookdev["atmosphere"]["profile"] == style["atmosphere_profile"], "Atmosphere profile mismatch")
    render = docs["render_plan"]
    require(render["camera"]["location"] != render["camera"]["target"], "Camera location and target must differ")
    require(render["camera"]["profile"] == style["camera_profile"], "Camera profile mismatch")
    require(render["color"]["profile"] == style["color_profile"], "Color profile mismatch")
    metadata = docs["render_metadata"]
    require(metadata["render_plan_id"] == render["document_id"], "Unknown render plan")
    require(metadata["render_plan_hash"] == document_hash(render), "Render plan hash mismatch")
    require(metadata["style_profile"] == style["style_profile"], "Render style mismatch")
    require(metadata["renderer"] == render["renderer"], "Renderer mismatch")
    require(metadata["render_success"], "Failed render cannot enter a visual review bundle")
    require(metadata["image"]["path"] == render["output"]["image_path"], "Render image path mismatch")
    review = docs["visual_review"]
    require(review["render_metadata_id"] == metadata["document_id"], "Unknown reviewed render metadata")
    require(review["image_sha256"] == metadata["image"]["sha256"], "Reviewed image hash mismatch")
    revision = docs["revision_plan"]
    require(revision["based_on_review_id"] == review["document_id"], "Unknown revision review")
    require(revision["render_metadata_id"] == metadata["document_id"], "Unknown revision render metadata")
    require(review["decision"] == "revision_required", "Revision plan requires a revision diagnosis")
    require(revision["pass_index"] < revision["max_preview_passes"], "Preview pass limit exceeded")
    require(revision["pass_index"] == int(metadata["pass_id"].split("_")[1]) + 1, "Revision pass is not the next pass")
    suggested = {(a["action"], a["scope"]) for a in review["recommended_actions"]}
    for action in revision["actions"]:
        require((action["action"], action["scope"]) in suggested, "Revision action not recommended by review")
    for edge in bundle["transitions"]:
        check_scene_transition(edge["current"], edge["target"])
    return bundle
