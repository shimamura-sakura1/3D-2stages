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
from runtime.planning import create_project, new_task
from runtime.stage1_executor import Stage1Executor
from runtime.stage2_executor import Stage2Executor


def parser():
    cli = argparse.ArgumentParser(description="Controlled two-stage 3D workflow")
    sub = cli.add_subparsers(dest="command", required=True)
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
        run.add_argument("--blender", default="blender")
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
    stage2.add_argument("--blender", default="blender")
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
