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
- docs/v02/baseline.md
- docs/v02/contracts.md
- docs/v02/quickstart.md
- prompts/parent.md
- prompts/asset_planner.md
Optional Tools:
- runtime/cli.py
- scripts/check_contracts.py
- scripts/check_visual_contracts.py
Action:
- Refine the brief, record assumptions, decompose assets/procedural geometry and choose the requested mode. Use the current isolated Python on macOS or Windows; doctor reports local discovery only. Create tasks and the manifest through the CLI. Contract audit is an optional structural check of sample documents, not asset approval.
- For new visual scenes, use the v0.2 quickstart and Step 0V with init-v02. The dated v0.1 baseline records historical evidence only. Existing init/run/stage1/stage2 remain schema 0.1 compatibility commands and are deprecated as the entry for new visual scenes. Read-only migrate-v02 produces a candidate, not an installed project; audit and transition checks grant no approval or execution.
Next:
- Step 0V
- Step 2
- END

### Step 0V — Establish visual direction
Type: agent
Read:
- docs/v02/planning.md
- docs/v02/quickstart.md
- templates/v02_stage0.yaml
- examples/v02/reference.svg
- examples/v02/reference_source.yaml
- examples/v02/LICENSE.md
- prompts/visual_director.md
- prompts/reference_interpreter.md
- prompts/scene_planner.md
Optional Tools:
- runtime/cli.py
Action:
- For new or explicit v0.2 work, interpret the brief and actual references, assign scoped roles and author the four Stage 0 contracts. Import references and submit through the versioned CLI. Present the concrete direction at visual_review_required. Record only the user's explicit decision against the current snapshot. Default plan_only does not authorize acquisition or rendering.
Next:
- Step 2
- END

### Step 2 — Select the authorized stage
Type: agent
Read:
- docs/workflow.md
- docs/hy3d-provenance.md
Optional Tools:
- runtime/cli.py
Action:
- Read the validated manifest. plan_only ends with the plan. stage1_only/full_pipeline perform pending assets. stage2_only uses supplied valid assets. repair selects affected work. Never infer approval from the mode.
- For schema 0.2, Stage 0 submission and explicit visual review are supported. Use Step 1G for authorized geometry acquisition. Separated scene setup and formal preview use Steps 5V and 6V; migration installation remains unavailable; do not route a 0.2 project into legacy execution.
If Stage 1 work is authorized:
- Go to Step 3
Otherwise:
- Go to Step 1G
- Go to Step 5
- END

### Step 1G — Acquire and review scene geometry
Type: agent
Read:
- docs/v02/geometry.md
- docs/v02/hy3d-surface.md
- docs/v02/hy3d-image-conditioning.md
- docs/hy3d-provenance.md
Optional Tools:
- runtime/cli.py
Action:
- For an approved v0.2 visual direction and authorized execution mode, define explicit geometry requests for scene objects, search configured libraries and acquire through A/B/C/D. Prefer the six bounded primitives for supported structures. Preserve provenance and surface sources; do not authorize generation from unknown reference rights. Use generate_geometry for Route C; only an explicit surface_evidence request invokes generate_surface_source. Validate both required gateway capabilities and rights before inference; retain paint as reference_only with its original bytes and separate geometry linkage. Inspect actual geometry and record the user's complete geometry review before proceeding to Blender production. A generated test double is only maintenance evidence, never a claim of real GPU production.
- For an image-only gateway, explicitly set image_only with exactly one licensed image reference and an empty task.hy3d.prompt. Keep target.description as semantic metadata; reject incompatible model conditions before inference. Preserve the conditioning mode and reference hash in the recipe and report only safe HTTP status/code diagnostics.
Next:
- Step 5V
- END

### Step 5V — Build separated Blender layers
Type: agent
Read:
- docs/v02/production.md
- docs/v02/style-refinement.md
Optional Tools:
- runtime/cli.py
Action:
- For v0.2 approved geometry, author the separate blockout/material/lookdev/render plans, prepare the MCP packet and execute only its registered semantic operations. Preserve the user's open scenes. Inspect actual output and unchanged geometry fingerprints when adjusting materials, lighting or camera. Complete setup only from current real receipts; rendering does not grant artistic approval.
- When explicitly selecting industrial_acg_v1 profile_version 1.1.0, apply its bounded eleven-dimension signature and scoped critic rubric; preserve 1.0.0 as the default and inspect material separation, daylight hierarchy and approved geometry before review.
Next:
- Step 6V
- END

### Step 6V — Record a formal preview
Type: agent
Read:
- docs/v02/preview.md
Optional Tools:
- runtime/cli.py
Action:
- After verified scene setup, reserve a preview pass and run its guarded MCP job. Wait for the actual worker receipt, inspect the PNG and finalize only current valid output. Preserve failed and successful pass history. Report render_success separately from artistic quality; continue to Step 7V for current-preview diagnosis.
Next:
- Step 7V
- END

### Step 7V — Diagnose the rendered image
Type: agent
Read:
- docs/v02/visual-review.md
- prompts/render_critic.md
Optional Tools:
- runtime/cli.py
Action:
- Read review-context and view its actual PNG. Diagnose the nine rubric categories using subjective problem-severity scores and visible evidence. Submit a current versioned visual_review; stale or unavailable evidence requires reinspection. Criticism only observes, diagnoses and recommends: it never changes Blender or grants final approval. For visual_revision continue to Step 8V; for final_review_required continue to Step 6 with the image and diagnosis for explicit final user review. When returning here after a final rejection, submit one new concrete revision_required diagnosis for the same current render before continuing to Step 8V.
Next:
- Step 6
- Step 8V
- END

### Step 8V — Apply a bounded visual revision
Type: agent
Read:
- docs/v02/controlled-revision.md
Optional Tools:
- runtime/cli.py
Action:
- In visual_revision, select only current review recommendations within the six supported visual actions. Submit the exact current revision_plan using revision-apply and expected-version. The controller preserves geometry and approvals and writes new visual plan versions. Use at most three total preview attempts, including failures; at the ceiling or for geometry/regeneration recommendations, stop and present the concrete issue for user review. Preparation alone is not rendering or artistic approval.
Next:
- Step 6V

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
- docs/v02/style.md
- docs/v02/style-refinement.md
Optional Tools:
- runtime/cli.py
Action:
- For style calibration or material inspection, resolve explicit classes/conditions with style-resolve and apply the registered Blender style worker. Inspect the actual calibration PNG before treating the six-material foundation as visually ready. This standalone calibration does not advance a project manifest.
- For the explicit 1.1.0 refinement, use style-resolve --version 1.1.0 and its isolated resources; read the signature's scoped evidence and inspect the seven-class calibration. Codex design review never substitutes for user artistic approval.
- Supply the explicit Blender plan and run preflight. Require Blender 4.2+ (4.5 LTS deployment baseline), independently of remote HY3D's bpy version. Check the current host's MCP tools and addon; execute prepared steps, inspect asynchronous status, and call stage2-complete only when real files exist. Regenerate machine-specific MCP packets after moving a project between macOS and Windows. Preserve open scenes. Batch is an explicit choice, not a fallback for disconnected MCP.
Next:
- Step 6
- END

### Step 6 — Final review and delivery
Type: agent
Read:
- docs/v02/delivery.md
- docs/workflow.md
- docs/hy3d-provenance.md
Optional Tools:
- runtime/cli.py
Action:
- For schema 0.2, use `final-review-context` to inspect the current immutable completed preview, critic and provenance snapshot, then record only the explicit user decision with `final-review-v02`. On approval use `deliver-v02` with the current expected version to publish the verified local package. On a final rejection, return to Step 7V for one new concrete revision-required critic; then continue through Step 8V for the existing bounded revision flow before a new preview and final review. No remote generation or artistic approval is implied by successful checks.
- Review the actual preview/scene and record approval before scene delivery. Deliver current valid files with provenance. Asset-only delivery can follow Stage 1 approval. Web delivery remains unsupported. Return concrete outputs or the precise pending action.
Next:
- Step 7V
- END

## Supporting boundaries

See [README.md](README.md) for formal commands, [platform guidance](docs/platforms.md) for local discovery, and [the gateway protocol](docs/hy3d_gateway.md) for HY3D over SSH. Deployment reports and earlier smoke runs are evidence for their recorded machine and scope only. Verify current connectivity, capabilities, input/output rights and actual files; a direct inference-client smoke run does not establish a complete Stage 1 lifecycle or artistic approval.

Workers submit isolated proposals; only ManifestManager writes official state. Python role checks and governance test copies are not OS sandboxes. This version has no parallel worker scheduler.

Governance version is recorded in interface.json and accepted changes; it is separate from default production schema_version 0.1, opt-in visual schema 0.2, and Python package version 0.1.0. See [MIGRATION.md](docs/governance/MIGRATION.md) for historical evidence scope, [v0.2 contracts](docs/v02/contracts.md) for current Phase 1 limits, and requirements.json for unresolved claims.
