# Two-Stage 3D Asset & Scene Builder Skill — Codex Build Specification v0.1

## 0. Purpose

This document defines the first implementation specification for a Codex-built Skill that supports 3D asset acquisition, AI-assisted 3D generation/refinement, Blender-based scene construction, and optional final delivery.

The system is intentionally **not a fully end-to-end black-box pipeline**. It must support explicit stage selection, human review, iteration, and rework.

The system consists of:

- **Parent Orchestrator**: understands user intent, improves prompts, decomposes scenes, plans work, and coordinates workers.
- **Stage 1 — Asset Acquisition & Generation**: searches asset libraries first, then chooses one of three routes:
  1. use an existing asset directly;
  2. use an existing asset as a base and refine/retexture/regenerate with Hunyuan3D;
  3. generate a new asset from prompt/image with Hunyuan3D.
- **Stage 2 — Blender Assembly & Art Direction**: GPT/Codex operates Blender to clean, normalize, stylize, compose, light, and export the final scene or reusable asset.
- **Delivery Layer**: outputs a reusable asset, Blender scene, or web-deployable result depending on user choice.

The system must prioritize **controllability, explicit state, reproducibility, and reviewability** over maximum automation.

---

# 1. Core Design Principles

## 1.1 Asset-library-first

Before generating a new asset with Hunyuan3D, Stage 1 must first check whether a sufficiently suitable asset already exists in one or more configured asset libraries.

Generation from scratch is a fallback, not the default.

The default decision order is:

```text
User Requirement
      |
      v
Asset Search
      |
      +--> suitable asset found ------> Route A: Direct Asset
      |
      +--> usable base found ---------> Route B: Asset + HY3D Refinement
      |
      +--> no suitable base ----------> Route C: HY3D Generation
```

The router must consider:

- semantic fit;
- visual/style fit;
- geometry quality;
- topology/editability;
- texture quality;
- licensing;
- format compatibility;
- scale;
- expected cleanup cost;
- whether the asset can be legally modified;
- user constraints.

---

## 1.2 Two main stages, but Stage 1 has three routes

Externally, the system is still a two-stage workflow:

```text
Stage 1: Asset Acquisition / Generation
Stage 2: Blender Processing / Scene Construction
```

Internally, Stage 1 contains three mutually selectable routes.

### Route A — Library Direct

Use an existing asset with minimal processing.

Typical use:

- benches;
- street lamps;
- plants;
- generic furniture;
- generic buildings;
- common railway props;
- background objects.

Flow:

```text
Asset Search
   ->
Candidate Evaluation
   ->
Download / Import
   ->
Basic Validation
   ->
Approved Stage 1 Asset
```

---

### Route B — Library Asset + Hunyuan3D Refinement

Use an existing asset as a structural base, then use local or remote Hunyuan3D to improve or adapt it.

Possible refinement tasks:

- retexture;
- style conversion;
- texture regeneration;
- geometry variation;
- shape adaptation;
- filling missing geometry;
- generating a visually consistent variation;
- creating a new asset from rendered views of the base asset.

Flow:

```text
Asset Search
   ->
Base Asset Found
   ->
Normalize / Prepare
   ->
HY3D Refinement
   ->
Review
   ->
Approved Stage 1 Asset
```

This route should be preferred when the asset geometry is useful but its style or materials do not match the project.

---

### Route C — Hunyuan3D Generation From Scratch

Generate a new asset using:

- prompt only;
- reference image;
- prompt + reference image;
- multiple prepared views if supported.

Flow:

```text
Optimized Asset Prompt
   ->
Reference Preparation
   ->
HY3D
   ->
Mesh + Texture
   ->
Review
   ->
Revise or Approve
```

This route is appropriate when no suitable asset exists or when the requested object is project-specific.

---

## 1.3 Human-in-the-loop by default

Stage 1 is explicitly iterative.

A generated or acquired asset does not automatically become a Stage 2 input.

Each asset moves through:

```text
planned
  ->
searching / generating
  ->
review_required
  ->
approved
     or
revision_requested
  ->
rework
```

The user may approve, reject, or request modifications.

The system may recommend approval or rework, but the user remains the final authority unless the user explicitly requests automatic approval.

---

## 1.4 Do not rely on prompt obedience for critical rules

Skill instructions are a soft constraint.

Critical workflow rules must also be enforced structurally through:

1. schemas;
2. state machines;
3. validators;
4. tool wrappers;
5. restricted write permissions;
6. stage executors.

General rule:

> If a rule can be checked programmatically, it should not exist only as natural-language instruction.

---

# 2. Top-Level Architecture

```text
                         User
                          |
                          v
                  Parent Orchestrator
                          |
             +------------+-------------+
             |                          |
             v                          v
      Requirement Model           Project Manifest
             |
             v
      Scene / Asset Planner
             |
       Parallel Asset Tasks
             |
             v
   +---------------------------+
   | Stage 1 Asset Router      |
   +---------------------------+
       |          |          |
       v          v          v
    Route A    Route B    Route C
    Library   Library+HY  HY Generate
       |          |          |
       +----------+----------+
                  |
                  v
            Stage 1 Review
                  |
             approved only
                  |
                  v
      +--------------------------+
      | Stage 2 Blender Builder  |
      +--------------------------+
                  |
                  v
             Final Review
                  |
                  v
            Delivery Layer
         /         |          \
      Asset      Scene        Web
```

---

# 3. Execution Modes

The Skill must support explicit user-selected execution modes.

## 3.1 `plan_only`

Only interpret requirements, improve prompts, decompose the scene, and create the plan.

No asset search, generation, or Blender execution.

---

## 3.2 `stage1_only`

Run asset planning, search, routing, generation/refinement, and Stage 1 review.

Do not build the Blender scene.

Useful for building a reusable asset library.

---

## 3.3 `stage2_only`

Use user-provided or previously approved assets and build/process them in Blender.

Stage 1 is skipped.

The Stage 2 preflight validator must verify that all required input assets exist.

---

## 3.4 `full_pipeline`

Run planning -> Stage 1 -> Stage 2 -> selected delivery.

Human review checkpoints remain active unless explicitly disabled by the user.

---

## 3.5 `repair`

Modify an existing project.

Examples:

- regenerate one asset;
- replace one asset;
- retexture an approved asset;
- rebuild lighting;
- change composition;
- re-export;
- switch delivery target.

Repair mode must never require rerunning unrelated tasks.

---

# 4. Proposed Skill Repository Structure

```text
two-stage-3d-skill/
|
|-- SKILL.md
|
|-- prompts/
|   |-- parent.md
|   |-- requirement_refiner.md
|   |-- asset_planner.md
|   |-- asset_search_worker.md
|   |-- route_b_refinement_worker.md
|   |-- route_c_generation_worker.md
|   |-- stage1_reviewer.md
|   |-- blender_builder.md
|   `-- final_reviewer.md
|
|-- contracts/
|   |-- project_manifest.schema.json
|   |-- asset_task.schema.json
|   |-- asset_candidate.schema.json
|   |-- stage1_result.schema.json
|   |-- blender_plan.schema.json
|   |-- review_report.schema.json
|   `-- delivery.schema.json
|
|-- policies/
|   |-- routing_policy.yaml
|   |-- stage_transitions.yaml
|   |-- asset_acceptance.yaml
|   |-- blender_rules.yaml
|   |-- licensing_policy.yaml
|   `-- output_rules.yaml
|
|-- runtime/
|   |-- manifest_manager.py
|   |-- state_machine.py
|   |-- validators.py
|   |-- asset_router.py
|   |-- asset_search.py
|   |-- hy3d_client.py
|   |-- stage1_executor.py
|   |-- stage2_executor.py
|   `-- delivery_executor.py
|
|-- providers/
|   |-- base.py
|   |-- sketchfab.py
|   |-- polyhaven.py
|   |-- local_library.py
|   |-- booth_manual.py
|   `-- hy3d.py
|
|-- templates/
|   |-- project_manifest.yaml
|   |-- asset_task.yaml
|   |-- style_bible.yaml
|   |-- blender_plan.yaml
|   `-- review_report.yaml
|
`-- tests/
    |-- test_routing.py
    |-- test_state_machine.py
    |-- test_manifest_validation.py
    `-- test_stage_boundaries.py
```

---

# 5. File Responsibilities

## 5.1 `SKILL.md`

`SKILL.md` is the constitution of the system.

It should stay relatively concise.

It defines:

- system purpose;
- stage boundaries;
- execution modes;
- authority hierarchy;
- mandatory use of manifest/contracts;
- asset-library-first rule;
- human-review rules;
- worker isolation rules;
- when parallelization is allowed;
- prohibited behavior.

It must NOT contain every implementation detail.

Implementation detail belongs in policies, prompts, schemas, and runtime code.

---

# 6. Parent Orchestrator

## 6.1 Parent responsibility

The Parent is the only agent with a global view of the project.

It is responsible for:

- understanding user intent;
- detecting beginner-level ambiguity;
- improving the user's description;
- identifying scene components;
- identifying reusable/procedural/generated components;
- creating groups;
- choosing how many workers are useful;
- creating task files;
- maintaining global consistency;
- presenting plans and revision summaries to the user.

The Parent should not directly perform Hy3D inference or Blender construction unless the implementation has no worker mechanism available.

---

## 6.2 Parent identity prompt

`prompts/parent.md` should contain a stable role definition similar to:

```text
You are the parent orchestration agent for a controlled 3D production workflow.

Your primary responsibility is to transform a user's potentially vague or inexperienced description into a structured and executable 3D production plan.

You are not a one-shot 3D generator.

You must:
- infer artistic intent without inventing major requirements;
- improve prompts for downstream 3D systems;
- decompose scenes into independent asset groups;
- identify which parts should use existing assets, procedural Blender construction, HY3D refinement, or HY3D generation;
- prefer existing legal and suitable assets over unnecessary generation;
- preserve project-wide style consistency;
- create structured task files for workers;
- maintain the project manifest through the Manifest Manager;
- expose meaningful review checkpoints;
- permit rework without restarting unrelated work;
- optimize for beginner accessibility and production controllability.

When a user's description is incomplete, convert it into explicit assumptions and record those assumptions in the project manifest.

Do not silently change the user's artistic intent.
```

---

# 7. Requirement Refinement

`prompts/requirement_refiner.md`

This prompt converts raw user input into a structured `user_brief`.

The refiner should extract or infer:

- scene type;
- visual style;
- emotional tone;
- time of day;
- era;
- geography;
- key objects;
- hero objects;
- background objects;
- desired realism;
- target platform;
- final output;
- animation requirements;
- scale;
- performance constraints;
- whether web deployment is required.

For beginners, it should also improve vague requests.

Example:

```text
User:
"做一个有点孤独感的乡下车站"

Refined:
"A quiet rural Japanese railway station at late afternoon, with restrained
anime-style materials, a small single platform, weathered station signage,
a wooden bench, sparse vegetation, and an empty track extending into the distance.
The composition should emphasize solitude and transitional space rather than realism."
```

The refined prompt must be shown to the user in planning/review mode before expensive generation unless the user has explicitly requested automatic execution.

---

# 8. Asset Planning

`prompts/asset_planner.md`

The planner decomposes a scene into work units.

Every component should be classified into one of:

```text
EXISTING_ASSET_CANDIDATE
HY3D_REFINEMENT_CANDIDATE
HY3D_GENERATION_CANDIDATE
BLENDER_PROCEDURAL
BLENDER_MANUAL
IGNORE_BACKGROUND_DETAIL
```

Example station decomposition:

```text
Station Building      -> existing asset search first
Platform              -> Blender procedural/manual
Bench                 -> existing asset search first
Station Sign          -> existing asset / HY3D refinement
Vending Machine       -> existing asset search first
Rail                  -> Blender procedural
Sleepers              -> Blender procedural
Vegetation            -> existing asset library
Clock                  -> existing asset search / HY3D generation
Lighting               -> Stage 2
Camera                 -> Stage 2
Atmosphere             -> Stage 2
```

The planner should avoid generating components that Blender can create more reliably through primitives, arrays, curves, geometry nodes, or procedural systems.

---

# 9. Parallel Workers

The Parent may spawn approximately 3–4 workers by default when a scene contains multiple independent asset groups.

Examples:

```text
Worker A -> architecture assets
Worker B -> railway props
Worker C -> environmental props
Worker D -> vegetation / decorative objects
```

Parallelism should be based on independence, not arbitrary splitting.

Workers must receive minimal relevant context:

```text
Global Style Bible
+
Assigned Asset Task
+
Relevant References
+
Provider Configuration
```

Workers must not receive unnecessary project history.

Workers must not directly modify the global manifest.

---

# 10. Global Style Bible

Each project should have:

`projects/<project_id>/style_bible.yaml`

Example:

```yaml
visual_style:
  target: anime_2_5d
  realism: low_to_medium
  silhouette_priority: high

geometry:
  detail_level: medium
  avoid_micro_geometry: true
  favor_clean_shapes: true

materials:
  pbr_complexity: restrained
  micro_surface_detail: low
  anime_shader_target: true

texture:
  desired_quality: high
  photorealism: false
  color_blocking: strong

lighting:
  physically_plausible: true
  artistic_priority: high

composition:
  cinematic: true
  environment_storytelling: true
```

All workers and Stage 2 must read the style bible.

---

# 11. Stage 1 Asset Task Contract

Every Stage 1 unit uses an `asset_task.yaml`.

Example:

```yaml
asset_id: station_bench_001
group_id: props

name: rural_station_bench
asset_role: supporting_prop

target:
  description: >
    Wooden bench for a small rural Japanese station platform.
  scale_hint:
    width_m: 1.8
    height_m: 0.82

style:
  source: style_bible
  overrides: {}

search:
  enabled: true
  preferred_providers:
    - local_library
    - sketchfab
    - polyhaven
  keywords:
    - railway bench
    - station bench
    - Japanese station bench

routing:
  preferred_route: auto
  allow_route_a: true
  allow_route_b: true
  allow_route_c: true

hy3d:
  enabled: true
  mode: auto
  reference_images: []
  prompt: null

review:
  required: true
  max_revisions: 3

status: planned
```

---

# 12. Asset Search Providers

Provider integrations must use a shared adapter interface.

Example conceptual interface:

```python
class AssetProvider:
    def search(self, query, filters):
        ...

    def get_metadata(self, asset_id):
        ...

    def acquire(self, asset_id, output_dir):
        ...
```

Supported providers may include:

- local reusable asset library;
- Sketchfab;
- Poly Haven;
- other future API-accessible libraries;
- manually acquired BOOTH/itch.io assets where automated API integration is unavailable.

The provider layer must be extensible.

The Skill must not hard-code only one asset library.

---

# 13. Route Decision Policy

`policies/routing_policy.yaml`

Suggested decision criteria:

```yaml
weights:
  semantic_fit: 0.25
  geometry_quality: 0.15
  style_fit: 0.15
  licensing: 0.15
  editability: 0.10
  texture_quality: 0.10
  cleanup_cost: 0.10

thresholds:
  direct_use_score: 0.80
  refinement_score: 0.55
```

Conceptual behavior:

```text
score >= 0.80
    -> Route A

0.55 <= score < 0.80 and geometry is usable
    -> Route B

score < 0.55
    -> Route C
```

The exact scoring method may evolve.

Licensing must be treated as a gate, not merely a preference.

An asset that fails licensing requirements must not be selected.

---

# 14. Route A — Direct Asset

Route A should:

1. search;
2. shortlist candidates;
3. validate license;
4. acquire asset;
5. inspect file format;
6. record provenance;
7. perform lightweight technical validation;
8. submit for review.

Output example:

```yaml
asset_id: station_bench_001
route: library_direct

source:
  provider: sketchfab
  source_asset_id: abc123
  license: cc_by
  attribution_required: true

files:
  model: stage1/outputs/station_bench_001.glb

status: review_required
```

---

# 15. Route B — Library + Hunyuan3D Refinement

Route B is a hybrid route.

Use when:

- source geometry is useful;
- style is wrong;
- texture quality is poor;
- visual language does not match the project;
- a project-specific variation is needed.

Possible implementation strategies:

### B1. Mesh-to-texture

Use existing mesh and regenerate textures.

### B2. Render-to-image-to-3D

Render standardized views from the source asset, stylize or modify reference imagery, then regenerate with HY3D.

### B3. Geometry adaptation

If supported by the selected HY3D backend, use geometry/shape conditioning or downstream repair tools.

Stage 1 must keep the original asset and the refined derivative separately.

Never overwrite source files.

Directory pattern:

```text
stage1/
  sources/
    station_bench_001_original.glb

  outputs/
    station_bench_001_rev01.glb
    station_bench_001_rev02.glb
```

---

# 16. Route C — Hunyuan3D Generation

Route C is the full-generation path.

Input:

- optimized prompt;
- optional reference image;
- project style bible;
- scale hint;
- technical constraints.

The HY3D client must abstract local and remote inference.

Conceptual configuration:

```yaml
hy3d_backend:
  type: local | remote

  local:
    endpoint: http://localhost:8080

  remote:
    endpoint: https://configured-endpoint.example
    auth_profile: hy3d_remote_default
```

Secrets must never be embedded in project manifests.

Use environment variables or credential storage.

---

# 17. Hunyuan3D Client

`runtime/hy3d_client.py`

The rest of the Skill must not care whether HY3D is local or remote.

Expose a stable interface:

```python
generate_shape(...)
generate_textured_asset(...)
retexture_mesh(...)
health_check(...)
```

Example conceptual call:

```python
result = hy3d.generate_textured_asset(
    prompt=task.prompt,
    reference_images=task.references,
    output_dir=task.output_dir,
)
```

Backend selection happens through configuration, not worker reasoning.

---

# 18. Stage 1 Review

`prompts/stage1_reviewer.md`

Review criteria:

- semantic correctness;
- silhouette;
- proportions;
- scale plausibility;
- geometry integrity;
- obvious holes/intersections;
- texture quality;
- texture-to-geometry alignment;
- style consistency;
- suitability for Blender cleanup;
- suitability for intended camera distance.

Review output must be structured.

Example:

```yaml
asset_id: station_bench_001
decision: revision_requested

scores:
  semantic_fit: 0.95
  silhouette: 0.88
  geometry: 0.75
  texture: 0.62
  style_consistency: 0.55

issues:
  - texture is too photorealistic
  - metal supports are overly detailed

revision_request:
  type: retexture
  instruction: >
    Reduce surface noise, simplify wood grain, and preserve large clean color blocks.
```

---

# 19. Stage 1 State Machine

Recommended asset states:

```text
planned
searching
candidate_found
route_selected
generating
review_required
revision_requested
reworking
approved
failed
```

Only runtime code may mutate official state.

Workers submit proposed results.

---

# 20. Project Manifest

Each project has one authoritative:

`projects/<project_id>/manifest.yaml`

The manifest is the interface between Stage 1 and Stage 2.

It records:

- user brief;
- assumptions;
- execution mode;
- scene groups;
- style bible path;
- asset tasks;
- approved assets;
- provenance;
- selected Stage 1 routes;
- revision history;
- Stage 2 plan;
- delivery target;
- project state.

Workers must never directly edit this file.

Only `manifest_manager.py` may write it.

---

# 21. Manifest Authority

Authority order:

```text
1. Current explicit user instruction
2. Validated project manifest
3. Contract schemas
4. Runtime policies
5. Style bible
6. Worker prompts
```

If a worker prompt conflicts with the manifest or schema, the worker prompt loses.

---

# 22. Stage 2 Entry Conditions

Stage 2 may begin only when one of the following is true:

### Normal pipeline

All required assets are `approved`.

### Stage 2 only

The user explicitly selected `stage2_only` and supplied valid assets.

### Partial scene mode

The user explicitly accepts missing assets or placeholders.

The validator must enforce this.

Natural-language instruction alone is insufficient.

---

# 23. Stage 2 Blender Processing

Stage 2 has two internal phases.

## 23.1 Technical Asset Normalization

For each imported asset:

- validate file;
- import;
- normalize units;
- normalize transform;
- set origin;
- inspect normals;
- inspect material slots;
- organize collections;
- rename objects;
- remove unnecessary cameras/lights;
- simplify if required;
- preserve provenance.

---

## 23.2 Scene Assembly & Art Direction

Using the user's prompt and approved plan:

- construct procedural geometry;
- assemble assets;
- place architecture;
- place props;
- create repeated structures;
- apply shared materials/shaders;
- establish camera;
- establish lighting;
- build atmosphere;
- make composition adjustments;
- optimize scene;
- prepare export.

The Blender builder should prioritize scene logic and composition, not merely object import.

---

# 24. Blender Procedural Preference

Stage 2 should prefer Blender procedural construction for geometry that AI generation handles poorly.

Examples:

- rail tracks;
- sleepers;
- fences;
- platform segments;
- roads;
- walls;
- repeated columns;
- cables;
- arrays;
- modular architecture;
- terrain repetition.

Prefer:

- primitives;
- curves;
- modifiers;
- Geometry Nodes;
- arrays;
- linked instances.

Do not generate these as dense AI meshes unless specifically required.

---

# 25. Blender Build Plan

`blender_plan.yaml`

Example:

```yaml
scene:
  name: rural_station_scene
  units: meters

collections:
  - Architecture
  - Railway
  - Props
  - Vegetation
  - Lighting

assets:
  station_bench_001:
    source: stage1/outputs/station_bench_001_rev02.glb
    collection: Props
    placement:
      zone: platform_waiting_area

procedural:
  railway_track:
    method: geometry_nodes
    gauge_m: 1.067

style:
  style_bible: style_bible.yaml
  unified_shader: anime_master

camera:
  intent: cinematic_eye_level
  focal_length_mm: 50

lighting:
  mood: quiet_late_afternoon
```

---

# 26. Final Review

Final review checks:

- required objects present;
- scene composition matches brief;
- asset scale is coherent;
- style consistency;
- no obvious broken materials;
- no accidental high-cost geometry;
- output format compatible;
- web export requirements if selected;
- attribution metadata if required.

The reviewer should generate a structured final report.

---

# 27. Delivery Layer

Delivery is separate from Stage 2.

Supported targets:

```text
asset
scene
web
```

---

## 27.1 Asset delivery

Possible outputs:

- `.glb`
- `.gltf`
- `.fbx`
- `.obj`
- `.blend`

The exporter must preserve scale and materials where possible.

---

## 27.2 Scene delivery

Output:

- `.blend`;
- optional asset package;
- textures;
- manifest;
- license / attribution record.

---

## 27.3 Web delivery

Possible targets:

- glTF/GLB + model-viewer;
- Three.js;
- Babylon.js;
- another configured web runtime.

Web deployment is not assumed.

It is selected by the user.

The system should distinguish:

```text
web_export
```

from:

```text
web_deploy
```

Export prepares web-compatible assets.

Deployment may require an external hosting/tool workflow.

---

# 28. Project Workspace

Recommended per-project structure:

```text
projects/<project_id>/
|
|-- manifest.yaml
|-- user_brief.md
|-- style_bible.yaml
|
|-- planning/
|   |-- scene_plan.yaml
|   `-- asset_groups.yaml
|
|-- stage1/
|   |-- tasks/
|   |-- candidates/
|   |-- sources/
|   |-- outputs/
|   `-- reviews/
|
|-- stage2/
|   |-- blender_plan.yaml
|   |-- scene/
|   `-- reviews/
|
`-- delivery/
    |-- config.yaml
    |-- attribution.yaml
    `-- outputs/
```

---

# 29. Constraint Strategy

Because Skill instructions alone are not strong enough, implementation must use three levels of constraints.

## 29.1 Soft constraints

Implemented in:

- `SKILL.md`;
- prompt files.

Used for:

- artistic judgment;
- planning behavior;
- preference ordering;
- communication style;
- decomposition strategy.

---

## 29.2 Structural constraints

Implemented in:

- JSON Schema;
- YAML contracts;
- validated manifests.

Used for:

- required fields;
- enum values;
- route selection;
- output structure;
- status formats;
- review results.

---

## 29.3 Hard runtime constraints

Implemented in Python/tool wrappers.

Used for:

- stage transitions;
- write permissions;
- asset approval gates;
- licensing gates;
- filesystem boundaries;
- credential handling;
- provider execution;
- allowed Blender actions;
- delivery validation.

Rule:

> Critical workflow safety must never depend solely on the model remembering an instruction.

---

# 30. Manifest Write Isolation

Only the Parent/Manifest Manager may modify the global manifest.

Parallel workers write isolated result files:

```text
stage1/results/worker_a.json
stage1/results/worker_b.json
stage1/results/worker_c.json
```

Then:

```text
worker outputs
      |
      v
validation
      |
      v
manifest manager
      |
      v
manifest.yaml
```

This prevents race conditions and conflicting state updates.

---

# 31. Tool Permission Boundaries

Recommended conceptual permissions:

```text
Parent
  - create tasks
  - read all project state
  - request stage execution
  - request transitions
  - update manifest through manager

Search Worker
  - asset-search tools
  - metadata read
  - candidate write

HY3D Worker
  - read asset task
  - call HY3D
  - write task output only

Reviewer
  - read output
  - write review result only

Blender Worker
  - Blender execution
  - stage2 workspace only

Manifest Manager
  - exclusive manifest write permission
```

Do not give all agents all tools.

---

# 32. Licensing and Provenance

Every externally acquired asset must record:

```yaml
source:
  provider: ...
  original_url: ...
  asset_id: ...
  creator: ...
  license: ...
  attribution_required: true | false
  modification_allowed: true | false
```

Route B must verify modification rights before refinement.

Stage 2 and Delivery must retain attribution metadata when required.

---

# 33. Retry / Rework Strategy

Do not automatically rerun expensive generation indefinitely.

Recommended defaults:

```yaml
max_generation_revisions: 3
max_search_expansions: 2
```

After repeated failure, Parent should:

- summarize failure;
- recommend switching route;
- recommend manual intervention;
- request user decision if needed.

Example:

```text
Route C failed twice
   ->
search again
   ->
possible Route B base found
   ->
recommend switching Route C -> Route B
```

---

# 34. Codex Implementation Priorities

Do not implement the complete framework at once.

Build an MVP first.

## MVP Phase 1

Required:

```text
SKILL.md
prompts/parent.md
prompts/asset_planner.md
contracts/project_manifest.schema.json
contracts/asset_task.schema.json
contracts/stage1_result.schema.json
policies/stage_transitions.yaml
runtime/manifest_manager.py
runtime/state_machine.py
runtime/asset_router.py
runtime/hy3d_client.py
runtime/stage1_executor.py
runtime/stage2_executor.py
templates/project_manifest.yaml
templates/style_bible.yaml
```

---

## MVP Phase 2

Add:

- real asset provider adapters;
- multiple asset search providers;
- parallel workers;
- Stage 1 reviewer;
- Blender build-plan schema;
- license manager;
- repair mode.

---

## MVP Phase 3

Add:

- automated web export;
- project dashboard;
- asset caching;
- asset reuse database;
- similarity search;
- automated scene QA;
- richer HY3D refinement strategies.

---

# 35. Required Tests

At minimum, Codex must implement tests for:

### Routing

```text
high-quality matching asset -> Route A
usable geometry / bad style -> Route B
no useful asset -> Route C
invalid license -> reject candidate
```

### Stage boundaries

```text
unapproved asset -> Stage 2 blocked
approved required assets -> Stage 2 allowed
stage2_only + supplied assets -> allowed
```

### Manifest

```text
worker cannot directly mutate manifest
invalid schema -> rejected
valid transition -> accepted
invalid transition -> rejected
```

### HY3D abstraction

```text
local backend
remote backend
health check failure
generation failure
```

---

# 36. Non-Goals for v0.1

The first implementation should NOT attempt:

- fully autonomous art direction;
- automatic deployment to arbitrary hosting providers;
- training/fine-tuning HY3D;
- perfect automatic topology repair;
- automatic licensing interpretation from arbitrary websites;
- complete replacement of user review;
- generating entire complex scenes as one HY3D object.

---

# 37. Final Behavioral Summary

The intended behavior is:

```text
1. User describes desired scene or asset.

2. Parent improves the description and extracts structured intent.

3. Parent decomposes the project into asset groups.

4. Stage 1 searches asset libraries first.

5. For each component, router chooses:
      A. existing asset directly
      B. existing asset + HY3D refinement
      C. HY3D generation from scratch

6. Workers may execute independent asset tasks in parallel.

7. Stage 1 results are reviewed and may be revised.

8. Only approved assets cross the Stage 1 / Stage 2 interface.

9. Stage 2 uses GPT/Codex + Blender for:
      cleanup
      normalization
      procedural geometry
      layout
      shader/style unification
      lighting
      camera
      composition

10. Final output is selected by the user:
      reusable asset
      Blender scene
      web-compatible result

11. Every important state transition is enforced by runtime code,
    not merely by Skill prompt instructions.
```

---

# 38. Primary Engineering Principle

The most important architectural rule for this Skill is:

> **The model decides what should happen; contracts describe what is valid; runtime code decides what is actually allowed to happen.**

This division is necessary because prompt-level Skill constraints alone are not sufficiently reliable for a multi-stage, multi-worker 3D production pipeline.
