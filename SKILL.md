---
name: two-stage-3d
description: Create and revise reviewable static 3D environments and Blender scenes from briefs or reference images, with visual planning, library-first geometry acquisition, unified look development, preview critique, bounded revision, and local delivery. Use for scene production or supported standalone asset work.
---

# Visual Scene Production Skill

A four-stage production workflow: **Stage 0 visual direction → Stage 1 geometry acquisition → Stage 2 scene and look development → Stage 3 visual critique and revision**, followed by explicit final review and local delivery. The invocation name `two-stage-3d` remains compatible; it does not describe the stage count. Stage numbers describe production responsibilities; the stable Step IDs below preserve existing links.

Codex owns intent, planning and artistic judgment. Runtime performs deterministic retrieval, validation, versioning and review gates; only ManifestManager writes official project state. Blender executes the scene operations. HY3D is an optional geometry/surface-source backend; final appearance belongs to the style system. This Skill owns orchestration; interface.json registers implementations and dependencies, not a second workflow engine.

Use for static environments, architecture and station prototypes, hard-surface props, or assembling existing assets. Current scope excludes animation/rigging, model training, automatic geometry regeneration during visual revision, and web publication. Detailed capabilities and evidence limits are in [README.md](README.md).

Current user instructions take precedence. Default `plan_only` permits planning, not acquisition or rendering. Execution mode and visual, geometry and final approvals are separate decisions: record only explicit user decisions for v0.2. Valid files, a critic recommendation, prepared packets and queued jobs never grant artistic approval or prove execution.

Resolve guide/template paths relative to this Skill's directory and scene output paths relative to the user's chosen project. Use an installed, isolated Python 3.11+ environment; pass absolute paths when the working directory differs. Keep each project's assets, manifests and renders in its project directory. Blender defaults to MCP; inspect host tools and preserve open scenes. MCP failure does not authorize batch fallback.

## Execution Router

### Step 1 — Identify the project and requested work
Type: agent
Read:
- docs/platforms.md
- docs/v02/quickstart.md
- prompts/parent.md
Optional Tools:
- runtime/cli.py
- scripts/check_contracts.py
- scripts/check_visual_contracts.py
Action:
- Optional contract audits inspect document structure only; they neither execute a scene nor approve it.
- Resolve the brief, project directory, references and authorized scope. For an existing project, read validated `status` before choosing a path; resume its current state rather than recreate it. Unknown or invalid schema requires a concrete error and END.
- New visual scenes enter Step 0V with `init-v02`; existing schema 0.2 projects resume at Step 2. Existing schema 0.1 projects, or explicitly requested legacy standalone asset work, enter Step L. Do not infer legacy mode from the compatible Skill name or an environment subject such as a station.
- Standalone style calibration enters Step C; it does not advance a project. Read-only `migrate-v02` produces a candidate requiring missing visual inputs, not an installed project or transferred approvals. `doctor` reports local discovery, not live Blender or GPU success.
Next:
- Step 0V
- Step 2
- Step L
- Step C
- END

### Step 0V — Stage 0: establish visual direction
Type: agent
Read:
- docs/v02/contracts.md
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
- Create only a new project with the entry below, substituting the intended directory, project ID and brief. Existing initialized or rejected plans retain their project and document history. Import with `reference-add-v02`, submit four authored documents with `stage0-submit`, and record an explicit direction decision with `visual-review-v02`, each against current evidence/version. The quickstart's reference and license are examples, not claims about the user's image.
```text
python -m runtime.cli init-v02 PROJECT --id PROJECT_ID --brief BRIEF
```
Next:
- Step 2
- END

### Step 2 — Resume the v0.2 scene by state and authorization
Type: agent
Read:
- docs/v02/contracts.md
Optional Tools:
- runtime/cli.py
Action:
- This dispatcher accepts schema 0.2 only. Use validated status, current artifact versions and existing explicit decisions; mode alone never implies approval. Record newly granted execution scope using `configure-v02` with expected-version. In plan_only, continue requested Stage 0 work or show the pending plan and END; do not acquire or render.
- initialized/visual_planning/visual_review_required returns to Step 0V to author, revise or present the current direction. Already approved direction must not be resubmitted merely to resume geometry work.
- visual_approved/geometry_pending/geometry_review_required enters Step 1G. Acquire only when authorized and allowed by state; pending review presents existing geometry, and rejected geometry uses the bounded reacquisition path.
- In stage1_only, geometry_approved is the completed checkpoint: report the reviewed geometry and END. Scene setup and previews require authorized stage2_only/full_pipeline/repair scope. With that scope, geometry_approved/blockout_pending/lookdev_pending enters Step 5V; render_pending enters Step 6V; render_review_required enters Step 7V.
- In visual_revision, inspect the current critic and render first. A final rejection whose current critic still requests final review must return to Step 7V for one new revision_required diagnosis. Enter Step 8V only with a current, unused revision_required diagnosis. Read stage guides for setup/receipt recovery before retrying an incomplete operation.
- final_review_required/approved enters Step 6 for explicit final review or approved delivery. delivered normally reports the existing verified package and END; an explicit package verification/retrieval request can enter Step 6. Missing prerequisites remain pending; never replace the v0.2 command with legacy run/stage1/stage2.
Next:
- Step 0V
- Step 1G
- Step 5V
- Step 6V
- Step 7V
- Step 8V
- Step 6
- END

### Step 1G — Stage 1: acquire and review geometry
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
- Execute one declared object with the CLI below; REQUEST contains the authored geometry request and CATALOG is a configured library catalog. Add `--hy3d-config` only when needed. The current geometry/surface behavior in the HY3D guides extends the historical Phase 4 description.
```text
python -m runtime.cli geometry-acquire PROJECT --request REQUEST --catalog CATALOG
```
- `geometry-review-v02` records the user's decision for the complete current geometry set. Partial acquisition can continue here; rejection preserves versions and permits bounded reacquisition. With stage1_only, stop after geometry review. Continue to Step 5V only with geometry approval and authorized scene execution.
Next:
- Step 1G
- Step 5V
- END

### Step 5V — Stage 2: build separated Blender layers
Type: agent
Read:
- docs/v02/production.md
- docs/mcp_and_ssh.md
- docs/v02/style-refinement.md
Optional Tools:
- runtime/cli.py
Action:
- For v0.2 approved geometry, author the separate blockout/material/lookdev/render plans, prepare the MCP packet and execute only its registered semantic operations. Preserve the user's open scenes. Inspect actual output and unchanged geometry fingerprints when adjusting materials, lighting or camera. Complete setup only from current real receipts; rendering does not grant artistic approval.
- When explicitly selecting industrial_acg_v1 profile_version 1.1.0, apply its bounded eleven-dimension signature and scoped critic rubric; preserve 1.0.0 as the default and inspect material separation, daylight hierarchy and approved geometry before review.
- Use `scene-plans-submit`, `scene-prepare` and, after real MCP execution, `scene-setup-complete`. Preparation is not completion. Stage2-only requires the approved v0.2 geometry records expected by runtime; supplied legacy files alone do not satisfy that gate. See the production guide for receipt recovery and exact arguments.
Next:
- Step 6V
- END

### Step 6V — Stage 2: render and record the actual preview
Type: agent
Read:
- docs/v02/preview.md
Optional Tools:
- runtime/cli.py
Action:
- After verified scene setup, inspect the existing current preview job before reserving a pass. On resume, an already running job is awaited; a completed current receipt is collected with `preview-complete`. A prepared but unstarted job may be executed once under existing authorization. Missing or stale output is not success; diagnose it without automatically reserving a replacement.
- Use `preview-prepare` only for an authorized new preview attempt, within the existing total budget, then execute its guarded MCP job. Wait for the actual worker receipt, inspect the PNG and use `preview-complete` to finalize only current valid output. Preserve failed and successful pass history. A recorded failure remains pending for diagnosis; report render_success separately from artistic quality. Continue to Step 7V only for a successful current preview.
Next:
- Step 7V
- END

### Step 7V — Stage 3: diagnose the rendered image
Type: agent
Read:
- docs/v02/visual-review.md
- prompts/render_critic.md
Optional Tools:
- runtime/cli.py
Action:
- Read review-context and view its actual PNG. Diagnose the nine rubric categories using subjective problem-severity scores and visible evidence. Use `visual-review-submit` to submit a current versioned visual_review; stale or unavailable evidence requires reinspection. Criticism only observes, diagnoses and recommends: it never changes Blender or grants final approval. For visual_revision continue to Step 8V; for final_review_required continue to Step 6 with the image and diagnosis for explicit final user review. When returning here after a final rejection, submit one new concrete revision_required diagnosis for the same current render before continuing to Step 8V.
Next:
- Step 6
- Step 8V
- END

### Step 8V — Stage 3: apply a bounded visual revision
Type: agent
Read:
- docs/v02/controlled-revision.md
Optional Tools:
- runtime/cli.py
Action:
- In visual_revision, select only current review recommendations within the six supported visual actions. Submit the exact current revision_plan using revision-apply and expected-version. The controller preserves geometry and approvals and writes new visual plan versions. Use at most three total preview attempts, including failures; at the ceiling or for geometry/regeneration recommendations, stop and present the concrete issue for user review. Preparation alone is not rendering or artistic approval.
Next:
- Step 6V

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
- For schema 0.1 compatibility only, review the actual preview/scene and record approval before scene delivery. Deliver current valid files with provenance. Asset-only delivery can follow Stage 1 approval. Web delivery remains unsupported. Return concrete outputs or the precise pending action.
Next:
- Step 7V
- END
### Step L — Select explicit v0.1 compatibility work
Type: agent
Read:
- docs/workflow.md
- docs/v02/baseline.md
- prompts/asset_planner.md
- docs/hy3d-provenance.md
Optional Tools:
- runtime/cli.py
Action:
- Enter only for an existing schema 0.1 project or explicitly requested legacy asset workflow. New compatibility projects use `init`; plan_only ends after the plan. Preserve explicit plan approval, per-asset review, acquisition order and delivery target rules in the legacy guide. Do not send schema 0.2 here.
- For approved existing assets awaiting review or delivery, go to Step 4 or Step 6 respectively. Authorized stage2_only uses valid supplied assets via Step 5. full_pipeline continues from approved asset work to authorized assembly; repair chooses only affected work. Missing approval stops at the relevant review gate.
If pending legacy acquisition is authorized and its plan is approved:
- Go to Step 3
Otherwise:
- Go to Step 4
- Go to Step 5
- Go to Step 6
- END

### Step 3 — v0.1 compatibility: acquire one asset
Type: tool
Tool:
- runtime/cli.py
Action:
- Execute stage1 for an explicit asset ID with configured libraries and optional HY3D config. Deployment-specific gateway and SSH values come from the ignored repository-root `.env`; checked-in YAML contains environment references only. Search first, apply formal A/B/C policy, and preserve sources, outputs and provenance. Missing providers or SSH configuration stop execution.
```text
python -m runtime.cli stage1 PROJECT --asset-id ASSET_ID --catalog CATALOG
```
Next:
- Step 4

### Step 4 — v0.1 compatibility: review the concrete asset
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

### Step 5 — v0.1 compatibility: assemble and verify in Blender
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

### Step C — Inspect or calibrate a standalone style
Type: agent
Read:
- docs/v02/style.md
- docs/v02/style-refinement.md
- docs/platforms.md
Optional Tools:
- runtime/cli.py
Action:
- For style calibration or material inspection, resolve explicit classes/conditions with style-resolve and apply the registered Blender style worker. Inspect the actual calibration PNG before treating the six-material foundation as visually ready. This standalone calibration does not advance a project manifest.
- For the explicit 1.1.0 refinement, use style-resolve --version 1.1.0 and its isolated resources; read the signature's scoped evidence and inspect the seven-class calibration. Codex design review never substitutes for user artistic approval.
- Execute the registered style worker through the available Blender MCP only when authorized. Inspect real output, preserve open scenes, and report this as standalone calibration evidence. Return to the user's requested task without creating or advancing scene approvals.
Next:
- END

## Maintenance and evidence boundaries

Ordinary scene production uses this Router and needs no external governance checkout. Modifying the Skill requires AGENTS.md and [the maintenance procedure](docs/governance/EVOLVE.md), under the user's designated contract-govern-skil framework. Resolve that framework through explicit `--framework`, `CONTRACT_GOVERN_HOME`, then the sibling `contract-govern-skil` checkout. Report a missing framework instead of bypassing governance; use `scripts/govern.py` to preserve real projects and deployment configuration.

Actual host paths and credentials belong in ignored `.env` or host MCP settings, never shared templates. Moving a project between machines requires regenerating absolute-path MCP packets. Worker proposals remain isolated; Python role checks are not OS sandboxes, and this version has no parallel worker scheduler.

Report technical execution separately from visual acceptance. Deployment reports, test doubles, local protocol tests and real GPU/Blender runs each prove only their recorded scope. Verify current capabilities, input/output rights and actual files; the pending real HY3D experiment must not be represented as passed. Read [gateway protocol](docs/hy3d_gateway.md) and [provenance rules](docs/hy3d-provenance.md) when that backend is selected.

New visual scenes use Schema 0.2 through `init-v02`; `init` retains Schema 0.1 compatibility. Governance version in interface.json, Python package version, production schemas and style profile versions are independent. Formal acceptance is established by tool-generated `changes/` records in the maintenance checkout; runtime distributions omit that history. See requirements.json for unresolved claims and README.md for capability and evidence scope.
