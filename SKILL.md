---
name: two-stage-3d
description: Build reviewable 3D assets and Blender scenes through library-first acquisition, optional remote Hunyuan3D generation, explicit asset review, and reproducible scene plans.
---

# Two-Stage 3D

The agent owns intent and artistic decisions. Contracts describe valid data; runtime code enforces formal constraints. This file owns orchestration. interface.json registers actual implementations and dependencies, not another workflow engine.

Current user instructions take precedence. Apply them through validated manifest operations; do not bypass runtime gates by editing official state. Every modification of this Skill must strictly follow the user's designated contract-govern-skil framework (on this Mac: /Users/tachibanakanade/contract-govern-skil). Read AGENTS.md and [the maintenance procedure](docs/governance/EVOLVE.md) before edits. Use the router below when producing assets/scenes; maintenance governance is not another production router.

## Execution Router

### Step 1 — Understand and plan
Type: agent
Read:
- docs/workflow.md
- docs/platforms.md
- prompts/parent.md
- prompts/asset_planner.md
Optional Tools:
- runtime/cli.py
- scripts/check_contracts.py
Action:
- Refine the brief, record assumptions, decompose assets/procedural geometry and choose the requested mode. Use the current isolated Python on macOS or Windows; doctor reports local discovery only. Create tasks and the manifest through the CLI. Contract audit is an optional structural check of sample documents, not asset approval.
Next:
- Step 2

### Step 2 — Select the authorized stage
Type: agent
Read:
- docs/workflow.md
Optional Tools:
- runtime/cli.py
Action:
- Read the validated manifest. plan_only ends with the plan. stage1_only/full_pipeline perform pending assets. stage2_only uses supplied valid assets. repair selects affected work. Never infer approval from the mode.
If Stage 1 work is authorized:
- Go to Step 3
Otherwise:
- Go to Step 5
- END

### Step 3 — Acquire one asset
Type: tool
Tool:
- runtime/cli.py
Action:
- Execute stage1 for an explicit asset ID with configured libraries and optional HY3D config. Deployment-specific gateway and SSH values come from the ignored repository-root `.env`; checked-in YAML contains environment references only. Search first, apply formal A/B/C policy, and preserve sources, outputs and provenance. Missing providers or SSH configuration stop execution.
Next:
- Step 4

### Step 4 — Review the concrete asset
Type: agent
Read:
- docs/workflow.md
- prompts/stage1_reviewer.md
Optional Tools:
- runtime/cli.py
Action:
- Inspect actual quality and provenance. Record the user's decision or explicitly authorized automatic review. Continue independent assets or request bounded rework through Step 3. After approval, go directly to Step 6 for asset delivery, or to Step 5 for authorized scene construction. End here when only Stage 1 review was requested. Never advance a listed unapproved asset.
Next:
- Step 3
- Step 5
- Step 6
- END

### Step 5 — Assemble and verify in Blender
Type: agent
Read:
- docs/workflow.md
- prompts/blender_builder.md
- docs/mcp_and_ssh.md
Optional Tools:
- runtime/cli.py
Action:
- Supply the explicit Blender plan and run preflight. Require Blender 4.2+ (4.5 LTS deployment baseline), independently of remote HY3D's bpy version. Check the current host's MCP tools and addon; execute prepared steps, inspect asynchronous status, and call stage2-complete only when real files exist. Regenerate machine-specific MCP packets after moving a project between macOS and Windows. Preserve open scenes. Batch is an explicit choice, not a fallback for disconnected MCP.
Next:
- Step 6
- END

### Step 6 — Final review and delivery
Type: agent
Read:
- docs/workflow.md
Optional Tools:
- runtime/cli.py
Action:
- Review the actual preview/scene and record approval before scene delivery. Deliver current valid files with provenance. Asset-only delivery can follow Stage 1 approval. Web delivery remains unsupported. Return concrete outputs or the precise pending action.
Next:
- END

## Supporting boundaries

See [README.md](README.md) for formal commands, [platform guidance](docs/platforms.md) for local discovery, and [the gateway protocol](docs/hy3d_gateway.md) for HY3D over SSH. Deployment reports and earlier smoke runs are evidence for their recorded machine and scope only. Verify current connectivity, capabilities, input/output rights and actual files; a direct inference-client smoke run does not establish a complete Stage 1 lifecycle or artistic approval.

Workers submit isolated proposals; only ManifestManager writes official state. Python role checks and governance test copies are not OS sandboxes. This version has no parallel worker scheduler.

Governance version is recorded in interface.json and accepted changes; it is separate from production schema_version 0.1 and Python package version 0.1.0. See [MIGRATION.md](docs/governance/MIGRATION.md) for historical evidence scope and requirements.json for unresolved claims.
