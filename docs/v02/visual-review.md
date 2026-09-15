# Current-preview visual review

`review-context PROJECT` validates the current successful metadata, actual PNG, current Stage 0 and separated scene plans and returns an inspection context without changing state. It includes the nine-category style rubric, image path/hash and current manifest version. It does not generate an artistic diagnosis.

Codex views that exact image, follows `prompts/render_critic.md`, and authors the existing visual_review contract. Scores consistently mean problem severity, from 0 (no visible problem) to 1 (severe). The review must reference the current scene, metadata and image and use the next immutable revision.

`visual-review-submit PROJECT --review REVIEW.json --expected-version N` writes only through ManifestManager. The current pending preview can advance to visual_revision or final_review_required. Neither grants final approval; no Blender or model call runs. Legacy and plan_only projects cannot use this execution boundary.

Current artifact hashes, actual image bytes/PNG dimensions, metadata/render-plan links, object/action scopes, version and revision are rechecked under the manifest lock. Old images, failed renders, malformed reviews and changed inputs reject without official writes. Historical operation packets intentionally become stale after preview completion; review validates the current formal documents directly instead of replaying that packet.

Phase 7 adds diagnosis and persistence. Bounded execution is a separate Phase 8 responsibility. A suggested geometry or base-material change is a review need, never a reason to bypass the existing geometry and visual approval records.

## Phase 7 validation, 2026-09-14

Implemented: current-render context, nine-category rubric/prompt, guarded immutable review persistence and Router Step 7V. Production contract shapes remain unchanged. Impact covered the CLI and ManifestManager with their current-render dependencies. Backward-compatibility risk is restricted to the added v0.2 path; legacy gates and historical tests remain intact.

Tests executed: the first new test failed because review-context did not exist; 46 new critic cases subsequently passed, plus 24 focused historical preview/production cases. Full governance passed all 27 active groups; static validation has no warnings and declared/runtime contracts passed. Independent spec and code-quality reviews found no blockers. Original failure and final logs are retained in `.deps/v02-phase7/`.

Real external validation: Blender 4.5.13 LTS through MCP rendered the fixed uniform/glossy calibration fixture and a new formal station Preview 00. Two independent Codex image inspections both diagnosed plasticity, weak material separation and excessive uniformity; scores differed and are not objective metrics. The fixed PNG and raw observations are preserved in `tests/fixtures/v02/critic/`. The actual station image was separately viewed and its current review persisted through the public CLI, advancing only to visual_revision. Existing visual/geometry maintenance approvals were retained; no final approval was created.

Not implemented in this phase: automatic revision, HY3D surface integration or style refinement. Generated station geometry and prior visual/geometry approval inputs remain explicitly labeled maintenance simulations; no real remote GPU claim is made. Qualitative recurrence is demonstrated only on this fixture, not arbitrary renders. See `docs/v02/phase-7-evidence.json` for paths and image identity.

Next Phase Readiness = READY, subject to the successful tool-generated S12 acceptance record. No Phase 8 execution is attributed to Phase 7.
