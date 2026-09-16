import argparse
import json
import sys
from pathlib import Path

# Support a concrete script-path binding as well as python -m runtime.cli.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.local_library import LocalLibraryProvider
from runtime.delivery_executor import DeliveryExecutor
from runtime.errors import BoundaryError, WorkflowError
from runtime.hy3d_client import Hy3DClient
from runtime.io import load_data
from runtime.manifest_manager import ManifestManager
from runtime.planning import create_project, create_visual_project, new_task
from runtime.validators import require_legacy_manifest
from runtime.platform_support import environment_report
from runtime.stage1_executor import Stage1Executor
from runtime.stage2_executor import Stage2Executor


def parser():
    cli = argparse.ArgumentParser(description="Controlled two-stage 3D workflow")
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser('final-review-context', help='Read immutable current final review evidence').add_argument('project')
    final = sub.add_parser('final-review-v02', help='Record an explicit final user decision on the exact current snapshot')
    final.add_argument('project')
    final.add_argument('--decision', choices=['approved','rejected'], required=True)
    final.add_argument('--expected-version', type=int, required=True)
    delivery = sub.add_parser('deliver-v02', help='Package the approved completed preview and scene locally')
    delivery.add_argument('project')
    delivery.add_argument('--expected-version', type=int, required=True)
    sub.add_parser('review-context' , help='Read validated current render and style critic rubric').add_argument('project')
    revision = sub.add_parser('revision-apply', help='Apply bounded current-review corrections')
    revision.add_argument('project')
    revision.add_argument('--revision', required=True)
    revision.add_argument('--expected-version', type=int, required=True)
    critic = sub.add_parser('visual-review-submit', help='Record a current agent-authored render diagnosis without approving')
    critic.add_argument('project')
    critic.add_argument('--review', required=True)
    critic.add_argument('--expected-version', type=int, required=True)
    sub.add_parser('preview-prepare', help='Reserve a new preview pass and prepare MCP execution').add_argument('project')
    preview = sub.add_parser('preview-complete', help='Validate current worker output and record formal render metadata')
    preview.add_argument('project')
    preview.add_argument('--job', required=True)
    sceneplans = sub.add_parser('scene-plans-submit')
    sceneplans.add_argument('project')
    sceneplans.add_argument('--plans', required=True)
    sceneplans.add_argument('--expected-version', type=int, required=True)
    sub.add_parser('scene-prepare', help='Prepare guarded semantic Blender operations; does not execute Blender').add_argument('project')
    setup = sub.add_parser('scene-setup-complete')
    setup.add_argument('project')
    setup.add_argument('--packet', required=True)
    setup.add_argument('--sha256', required=True)
    geometry = sub.add_parser('geometry-acquire', help='Acquire one declared v0.2 scene object for review')
    geometry.add_argument('project')
    geometry.add_argument('--request', required=True)
    geometry.add_argument('--catalog', required=True)
    geometry.add_argument('--hy3d-config')
    geo_review = sub.add_parser('geometry-review-v02')
    geo_review.add_argument('project')
    geo_review.add_argument('--decision', choices=['approved','rejected'], required=True)
    geo_review.add_argument('--expected-version', type=int, required=True)
    configure0 = sub.add_parser('configure-v02', help='Explicit mode authorization; grants no review approval')
    configure0.add_argument('project')
    configure0.add_argument('--mode', choices=['plan_only','stage1_only','stage2_only','full_pipeline','repair'], required=True)
    configure0.add_argument('--expected-version', type=int, required=True)
    stage0 = sub.add_parser('stage0-submit', help='Validate and persist agent-authored Stage 0 documents for review')
    stage0.add_argument('project')
    stage0.add_argument('--proposal', required=True)
    stage0.add_argument('--expected-version', type=int, required=True)
    review0 = sub.add_parser('visual-review-v02', help='Record an explicit user decision on the current Stage 0 snapshot')
    review0.add_argument('project')
    review0.add_argument('--decision', choices=['approved','rejected'], required=True)
    review0.add_argument('--expected-version', type=int, required=True)
    reference = sub.add_parser('reference-add-v02', help='Import reference bytes and explicit roles, preserving source metadata')
    reference.add_argument('project')
    reference.add_argument('image')
    reference.add_argument('--id', required=True)
    reference.add_argument('--role', action='append', required=True)
    reference.add_argument('--source', required=True)
    style = sub.add_parser("style-resolve", help="Resolve a versioned Blender material without modifying a project")
    style.add_argument("--profile", default="industrial_acg_v1")
    style.add_argument("--version", default="1.0.0")
    style.add_argument("--material", required=True)
    style.add_argument("--condition", required=True)
    style.add_argument("--project", help="Resolve an explicitly imported project style before bundled styles")
    sub.add_parser('style-inspect', help='Validate a user package and report pending review/resources').add_argument('source')
    prepare = sub.add_parser('style-prepare', help='Prepare an isolated user-style calibration candidate for Blender MCP')
    prepare.add_argument('source')
    prepare.add_argument('--output', required=True)
    style_import = sub.add_parser('style-import', help='Import a complete style package into a visual project')
    style_import.add_argument('project')
    style_import.add_argument('source')
    style_import.add_argument('--expected-version', type=int, required=True)
    visual = sub.add_parser("init-v02", help="Create an initialized 0.2 plan_only visual project")
    visual.add_argument("project")
    visual.add_argument("--id", required=True)
    visual.add_argument("--brief", required=True)
    sub.add_parser("migrate-v02", help="Read-only legacy conversion draft; does not install or modify a project").add_argument("project")
    edge = sub.add_parser("scene-transition-check", help="Validate a 0.2 scene edge without changing any state")
    edge.add_argument("current")
    edge.add_argument("target")
    doctor = sub.add_parser("doctor", help="Report local platform, Python, Blender discovery and governance configuration; no service calls")
    doctor.add_argument("--blender", help="Explicit Blender executable to inspect")
    init = sub.add_parser("init", help="Create a reviewable plan; does not call providers")
    init.add_argument("project")
    init.add_argument("--id", required=True)
    init.add_argument("--brief", required=True)
    init.add_argument("--refined")
    init.add_argument("--mode", default="plan_only", choices=["plan_only", "stage1_only", "stage2_only", "full_pipeline", "repair"])
    init.add_argument("--asset", action="append", default=[], help="Asset ID; use --task for detailed requirements")
    init.add_argument("--task", action="append", default=[], help="Validated asset task YAML")
    for name in ("status", "approve-plan", "approve-final", "deliver"):
        sub.add_parser(name).add_argument("project")
    config = sub.add_parser("configure")
    config.add_argument("project")
    config.add_argument("--mode", choices=["plan_only", "stage1_only", "stage2_only", "full_pipeline", "repair"])
    config.add_argument("--auto-approve", action=argparse.BooleanOptionalAction, default=None)
    config.add_argument("--allow-partial", action=argparse.BooleanOptionalAction, default=None)
    config.add_argument("--target", choices=["asset", "scene", "web"])
    for name in ("stage1", "run"):
        run = sub.add_parser(name)
        run.add_argument("project")
        run.add_argument("--catalog", help="Local library catalog YAML")
        run.add_argument("--hy3d-config", help="Gateway config; credentials are environment references")
        run.add_argument("--asset-id", required=name == "stage1",
                         help="Execute only this asset and stop at the Stage 1 checkpoint")
        run.add_argument("--blender", help="Batch executable; otherwise use BLENDER_EXECUTABLE, PATH or native install locations")
        run.add_argument("--backend", choices=["mcp", "batch"], default="mcp")
        run.add_argument("--plan", default="stage2/blender_plan.yaml")
    review = sub.add_parser("review")
    review.add_argument("project")
    review.add_argument("asset_id")
    review.add_argument("--decision", required=True, choices=["approved", "revision_requested", "failed"])
    review.add_argument("--instruction", default="")
    review.add_argument("--issue", action="append", default=[])
    stage2 = sub.add_parser("stage2")
    stage2.add_argument("project")
    stage2.add_argument("--plan", default="stage2/blender_plan.yaml")
    stage2.add_argument("--blender", help="Batch executable; otherwise use BLENDER_EXECUTABLE, PATH or native install locations")
    stage2.add_argument("--backend", choices=["mcp", "batch"], default="mcp")
    stage2.add_argument("--dry-run", action="store_true")
    complete = sub.add_parser("stage2-complete", help="Validate actual MCP outputs and accept the build")
    complete.add_argument("project")
    complete.add_argument("--build-id", required=True)
    for name in ("ssh-check", "hy3d-health"):
        remote = sub.add_parser(name)
        remote.add_argument("--config", default="configs/hy3d_ssh.yaml")
    supply = sub.add_parser("supply", help="Import a user asset for stage2_only")
    supply.add_argument("project")
    supply.add_argument("asset_id")
    supply.add_argument("model")
    supply.add_argument("--source", required=True, help="YAML provenance metadata")
    return cli


def execute(args):
    if args.command == "style-resolve":
        from runtime.style_resolver import resolve_material
        return resolve_material(args.profile, args.material, args.condition, version=args.version, project_root=args.project)
    if args.command == 'style-inspect':
        from runtime.user_styles import inspect_style
        return inspect_style(args.source)
    if args.command == 'style-prepare':
        from runtime.user_styles import prepare_style
        return prepare_style(args.source, args.output)
    if args.command == 'style-import':
        return ManifestManager(args.project).import_style(args.source, expected_version=args.expected_version)
    if args.command == "scene-transition-check":
        from runtime.state_machine import check_scene_transition
        check_scene_transition(args.current, args.target)
        return {"status": "legal", "current": args.current, "target": args.target, "execution": "not_performed"}
    if args.command == "init-v02":
        return create_visual_project(args.project, args.id, args.brief)
    if args.command == "doctor":
        from runtime.env_config import load_dotenv
        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env")
        return environment_report(root, args.blender)
    if args.command in ("ssh-check", "hy3d-health"):
        config = load_data(args.config)
        if args.command == "ssh-check":
            from runtime.ssh_transport import check_remote
            return check_remote(config.get("ssh"))
        return Hy3DClient(config).health_check()
    if args.command == "init":
        tasks = [new_task(asset) for asset in args.asset] + [load_data(p) for p in args.task]
        return create_project(args.project, args.id, args.brief, args.mode, tasks, args.refined)
    manager = ManifestManager(args.project)
    if args.command == "status":
        return manager.read()
    if args.command == "migrate-v02":
        from runtime.migrations.v01_to_v02 import plan_migration
        return plan_migration(manager.read())
    if args.command == 'final-review-context':
        from runtime.visual_delivery import final_review_context
        return final_review_context(manager)
    if args.command == 'final-review-v02':
        return manager.final_review_v02(args.decision, expected_version=args.expected_version)
    if args.command == 'deliver-v02':
        return manager.deliver_v02(expected_version=args.expected_version)
    if args.command == 'review-context':
        from runtime.visual_review import current_render_context
        return current_render_context(manager)
    if args.command == 'revision-apply':
        return manager.apply_visual_revision(load_data(args.revision), expected_version=args.expected_version)
    if args.command == 'visual-review-submit':
        return manager.submit_render_review(load_data(args.review), expected_version=args.expected_version)
    if args.command in ('preview-prepare', 'preview-complete'):
        from runtime.preview_renderer import PreviewRenderer
        renderer = PreviewRenderer(manager)
        return renderer.prepare() if args.command == 'preview-prepare' else renderer.complete(args.job)
    if args.command == 'scene-plans-submit':
        return manager.submit_scene_plans(load_data(args.plans), expected_version=args.expected_version)
    if args.command == 'scene-prepare':
        from runtime.scene_production import prepare_scene
        return prepare_scene(manager)
    if args.command == 'scene-setup-complete':
        from runtime.scene_production import complete_setup
        return complete_setup(manager, args.packet, args.sha256)
    if args.command == 'configure-v02':
        return manager.configure_visual(args.mode, expected_version=args.expected_version)
    if args.command == 'geometry-review-v02':
        return manager.review_geometry(args.decision, expected_version=args.expected_version)
    if args.command == 'geometry-acquire':
        from runtime.geometry_acquisition import GeometryAcquisition
        gateway = Hy3DClient(load_data(args.hy3d_config)) if args.hy3d_config else None
        return GeometryAcquisition(manager, {'local_library': LocalLibraryProvider(args.catalog)}, gateway).run(load_data(args.request))
    if args.command == 'stage0-submit':
        return manager.submit_visual_plan(load_data(args.proposal), expected_version=args.expected_version)
    if args.command == 'visual-review-v02':
        return manager.review_visual(args.decision, expected_version=args.expected_version)
    if args.command == 'reference-add-v02':
        from runtime.reference_manager import import_reference
        return import_reference(manager, args.image, args.id, args.role, load_data(args.source))
    require_legacy_manifest(manager.read())
    if args.command == "approve-plan":
        return manager.approve_plan()
    if args.command == "configure":
        result = manager.configure(mode=args.mode, auto_approve=args.auto_approve, allow_partial=args.allow_partial)
        if args.target:
            result = manager.set_delivery_target(args.target)
        return result
    if args.command == "review":
        task = manager.read()["assets"][args.asset_id]
        return manager.review({"asset_id": args.asset_id, "revision": task["revision"], "decision": args.decision,
                               "issues": args.issue, "instruction": args.instruction, "reviewer": "user"})
    if args.command == "approve-final":
        return manager.approve_final()
    if args.command == "deliver":
        return DeliveryExecutor(manager).run()
    if args.command == "supply":
        return manager.supply_asset(args.asset_id, args.model, load_data(args.source))
    if args.command == "stage2":
        return Stage2Executor(manager, args.blender, backend=args.backend).run(args.plan, args.dry_run)
    if args.command == "stage2-complete":
        from runtime.blender_mcp import McpBlenderExecutor
        return McpBlenderExecutor(manager).complete(args.build_id)
    manifest = manager.read()
    if args.command == "run" and manifest["mode"] == "plan_only":
        return {"status": "plan_only", "user_brief": manifest["user_brief"], "assets": list(manifest["assets"])}
    if args.asset_id is not None:
        if manifest["mode"] == "stage2_only":
            raise BoundaryError("Stage 1 prohibited in stage2_only mode")
        if args.asset_id not in manifest["assets"]:
            raise BoundaryError(f"Unknown asset ID: {args.asset_id}")
    if manifest["mode"] != "stage2_only":
        providers = {"local_library": LocalLibraryProvider(args.catalog)} if args.catalog else {}
        hy3d = Hy3DClient(load_data(args.hy3d_config)) if args.hy3d_config else None
        executor = Stage1Executor(manager, providers, hy3d)
        if args.command == "stage1":
            return executor.run(args.asset_id)
        if args.asset_id is not None:
            executor.run(args.asset_id)
        else:
            for asset_id, task in manifest["assets"].items():
                if task["status"] in ("planned", "reworking", "revision_requested"):
                    executor.run(asset_id)
        manifest = manager.read()
        pending = [k for k, t in manifest["assets"].items() if t["required"] and t["status"] != "approved"]
        if (args.asset_id is not None or (pending and not manifest["allow_partial"])
                or manifest["mode"] == "stage1_only"):
            return {"status": "stage1_checkpoint", "pending_assets": pending}
    elif args.command == "stage1":
        raise BoundaryError("Stage 1 prohibited in stage2_only mode")
    return Stage2Executor(manager, args.blender, backend=args.backend).run(args.plan)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (WorkflowError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
