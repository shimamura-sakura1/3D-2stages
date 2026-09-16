# HY3D geometry and optional surface evidence

Use SKILL.md Step 1G. Shape supplies geometry; Paint supplies optional surface evidence. The existing SSH/HTTP protocol remains the transport. Legacy generate_shape, generate_textured_asset and retexture_mesh calls retain their existing endpoints.

The semantic client methods are:

- `generate_geometry(...)` → `generate_shape`.
- `generate_surface_source(mesh=..., ...)` → `retexture_mesh` on an explicit existing mesh. A missing mesh rejects; this method does not silently start a new textured generation.

For `geometry-acquire`, keep the current geometry request and optionally add `"surface_evidence": true`. Omitted or false preserves the geometry-only path. A true request is supported only on Route C and preflights both required gateway capabilities, selected reference rights and configured output rights before inference. No automatic expensive retries or endpoint fallback run after failure. An older geometry-only client adapter can still supply generate_shape without implementing the new semantic method.

The shape file remains the geometry result. Paint writes to a separate revision subdirectory. The result preserves the raw textured GLB as `surface_sources` with kind `hy3d_paint`, role `reference_only`, and its checksum. `recipe.surface_operation` records the semantic operation, gateway operation and exact input geometry checksum. The same configured backend provenance and verified output rights apply to both operations. A paint response must contain an embedded material texture attached to a mesh; a geometry-only GLB cannot masquerade as surface evidence. These lightweight checks establish declared texture/UV associations and embedded payload bounds; they are not a complete image decoder, topology audit or aesthetic review. Sparse UV, Draco and meshopt encodings are explicitly rejected until supported, including when an ordinary buffer declaration is also present. KHR_texture_transform coordinate-set overrides remain supported.

ManifestManager is the only formal result writer. The result awaits geometry review; generation success does not approve it. Invalid responses leave no formal accepted result, and raw-source changes invalidate later validation. Previous source files remain available for inspection.

Stage 2 continues to resolve semantic material classes through industrial_acg_v1. Original generated colors and shaders are not treated as final art direction. Non-null semantic-map surface_source blending remains unsupported; retained Paint is available for inspection and future explicit texture interpretation. The operation packet guards both geometry and raw-source bytes.

## Verification scope

The new tests cover explicit Paint, default geometry-only behavior, legacy APIs, capability/rights failures before generation, invalid/untextured responses, immutable source linkage and later tamper rejection. Transport responses in unit tests are labelled test doubles. Formal phase acceptance additionally requires a real HY3D asset rendered with its raw materials and with style-resolved materials under comparable conditions; images must be inspected and the geometry fingerprint compared.

Never supply a guessed `license_verified` or assign CC0 to unknown model outputs to make a test proceed. Refer to the configured verified provenance and the user's source information. Current evidence and any missing real inputs are recorded in phase-9-evidence.json.

## Current verification and next phase readiness

Implemented: semantic client methods, explicit optional Paint acquisition, separate raw-source retention with geometry linkage, and current-source validation. 44 new tests plus 37 related historical tests passed; the full 29 active groups passed outside the network-restricted sandbox. Initial failures, unsupported-encoding reproduction, and final logs are retained in `.deps/v02-phase9/`. Independent spec and code-quality reviews passed after repair.

Real external validation executed: the configured SSH gateway returned all three expected capabilities; Blender 4.5.13 LTS MCP is connected. No new remote inference or raw/style comparison was performed because reference and output rights remain unverified. A Blender comparison helper is prepared under `.deps/v02-phase9/` for use with a verified real textured result.

Not implemented in this phase: texture blending into final shaders, Phase 10 style refinement, or any new licensing exception. **Next Phase Readiness = NOT_READY** until real Gate 9 is satisfied and the tool accepts S14. The current accepted version remains S13; local S14 implementation is pending acceptance.
