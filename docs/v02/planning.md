# Stage 0 visual planning

The agent interprets intent and images using the three reasoning contracts in prompts/. They are roles within the existing agent, not additional agents or an alternative Router.

1. `init-v02 PROJECT --id industrial_station --brief "Quiet industrial station"` creates a plan_only project.
2. `reference-add-v02 PROJECT IMAGE --id ref_material --role material_language --source SOURCE.yaml` preserves bytes in references/user, generated or selected. SOURCE has kind, creator, license, license_verified and attribution; record unknown rights honestly. Import returns the reference record to include in the board. Its content-addressed path binds the actual image bytes without changing the accepted Reference Board schema.
3. Author one proposal mapping visual_brief, reference_board, scene_spec and style_assignment to the four Phase 1 contracts. Each document starts at revision 0 and shares project_id and scene_version. Choose the actual style version 1.0.0. Stage 0 does not synthesize artistic intent in Python.
4. `stage0-submit PROJECT --proposal PROPOSAL.yaml --expected-version 0` validates all data and references before writing. Immutable files live under stage0/rev_0000/; manifest.artifacts indexes the official paths. The state becomes visual_review_required, with no provider or Blender execution.
5. After the user's concrete decision, `visual-review-v02 PROJECT --decision approved|rejected --expected-version VERSION` binds that decision to current document hashes. Rejection returns to visual_planning. Resubmit all four documents with incremented revisions; old files and decisions remain. Do not treat tests' simulated review calls as real artistic approval.

All official state changes use ManifestManager. Lock/version checking serializes writes, while immutable documents are staged before the manifest commit; an interrupted filesystem write may leave unreferenced files but cannot silently replace an accepted revision. External file tampering is detected before review. Reference license recording is distinct from acquisition authorization. Default and legacy production remain unchanged; Phase 4 acquisition is a separate gate.

## Phase 3 validation, 2026-09-14

The first run failed all 10 new cases because the reference/planning API was missing; raw log `.deps/v02-phase3/first-failure.txt`. The final focused suite passed 11 cases. Validate returned no warnings; declared/runtime contracts and all 23 active test groups passed. The real local industrial_station sample imported the inspected Phase 2 PNG as material_language only and persisted four valid documents at visual_review_required, version 1, with no approval or acquisition. Paths and artifact hashes are recorded in `.deps/v02-phase3/representative.json`. Review decisions in automated tests are explicit simulations, not approval of this sample.
