# Controlled visual revision (Phase 8)

SKILL.md Step 8V is the production entry. Codex reads the current image and formal review, selects supported recommendations, and submits a bounded revision plan. The deterministic controller applies parameters, not aesthetic judgment. User final approval remains separate.

## Explicit loop

1. `review-context PROJECT`: inspect the actual current successful image and current documents.
2. `visual-review-submit PROJECT --review REVIEW --expected-version VERSION`: record the observed diagnosis.
3. `revision-apply PROJECT --revision PLAN --expected-version VERSION`: validate and persist the revision and newer visual plans through ManifestManager. This prepares work and enters `render_pending`.
4. `preview-prepare PROJECT`: reserve the next immutable pass and obtain its guarded MCP job. Execute the returned code through Blender MCP, wait for the actual worker receipt, then `preview-complete PROJECT --job JOB`.
5. Inspect the new PNG and return to Step 7V. A technical success does not grant artistic approval.

A revision must name the current review, metadata, scene, next revision and next pass; use fresh document IDs. Supported action/scope pairs are roughness variation/object ID, light intensity/lighting, light direction/lighting, fog amount/atmosphere, framing/camera and exposure/render. Each action is a recommendation from the current review, with increase/decrease and small/medium amount within the recommendation. Geometry replacement or HY3D regeneration requires a separate user-reviewed workflow.

## Limits and evidence

The controlled loop defaults to three total reserved previews (00, 01, 02). Failed attempts consume this budget. A lower selected limit persists; increasing it in a later revision cannot evade the original limit. Earlier standalone Phase 6 technical rerenders retain their explicit behavior until the controlled loop is entered. An exhausted loop stops for user review; it does not reserve another pass or manufacture final approval.

Blockout, geometry source/version and approval records are retained byte-for-byte. Current plan/image hashes and optimistic manifest versions prevent stale writes. Prior reviews, revisions, plans, images, metadata and failures remain available for comparison. Repeated application and unsupported scopes reject before formal mutation.

## Deterministic adjustments

| Action | Small / medium | Bound |
| --- | --- | --- |
| Roughness variation | Add/subtract 0.1 / 0.2 to the material variation scale | 0.5–2.0; omitted scale is 1 |
| Light direction | Rotate key and fill around the vertical axis by 5° / 10° | −45° to +45° from the profile |
| Light intensity | Move 1 / 2 positions in low, medium, high | Reject beyond endpoints |
| Fog amount | Move 1 / 2 positions in none, subtle, medium, dense | Reject beyond endpoints |
| Camera framing | Change camera-to-target distance by 5% / 10% | Increase widens the frame; target stays fixed |
| Exposure | Add/subtract 0.25 / 0.5 EV | −20 to +20 EV |

Out-of-range adjustments reject rather than silently clamping. Camera changes are relative to the current distance, so opposite directions are not exact inverse operations. Other additive adjustments reverse exactly within bounds. Unspecified optional fields preserve existing rendering behavior.

Real-operation results are recorded in `phase-8-evidence.json`. Test receipts are labelled test doubles; only the MCP station operation supports real-render claims.

## Phase 8 representative verification

Blender 4.5.13 LTS through MCP rendered Preview 01 from the existing formal Preview 00 review. A +5° light azimuth adjustment and −0.25 EV exposure change produced different image bytes while preserving the exact geometry fingerprint, blockout and approval history. The new image was viewed and its separate review persisted; it still requires visual work and no artistic approval was inferred. See phase-8-evidence.json for concrete paths and hashes.

The new suite has 42 cases; together with critic, preview and production history, 112 focused cases passed. First failures and final results are retained. Full governance results are recorded with the evidence before acceptance.

Malformed or stale input is rejected before artifact writes. The existing writer uses atomic file replacement but does not roll back a multi-file operation after an operating-system I/O failure; an orphaned artifact may require inspection before retry. This existing durability limitation is outside the Phase 8 malformed-input guarantee.

Final post-repair governance: all 28 active groups passed; static validation has no warnings, and declared/runtime contracts passed. Independent spec and quality review passed. Phase 8 is ready for formal S13 acceptance; Phase 9 real comparison still requires a usable textured HY3D asset with verified reference/output rights.
