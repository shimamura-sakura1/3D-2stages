# Render Director integration work record

The user requested external RenderContext/RenderDirection/RenderReview integration,
consumer documentation, a sensitive-data audit, a runtime-only production branch,
and push. The user explicitly limited this iteration to affected tests. Formal
acceptance (which necessarily runs all active history) is not claimed here.

Claims: deterministic context aggregation; bounds-based camera and relative light
compilation; immutable provenance; reviewed, bounded revisions preserving geometry
and user constraints; executable defaults isolated from visual priors; complete
consumer resources without maintenance material or private deployment data.

Router placement: Step 5V builds context and requests external analyze before plan
submission; Step 7V requests review against actual PNG; Step 8V requests refine
before the existing revision gate. Stage 0 retains intent, not world transforms.

External dependency: only public data contracts and agent entry points. No external
prompts, rules or memory implementation are imported into this repository.

Test-first and final results are recorded in the ignored .skillctl/reports directory.
Real external-agent visual judgement and live Blender execution require separate
evidence; deterministic fixture tests must not be presented as such evidence.

The former runtime framework-discovery helper now lives under scripts. The new
portable requirement explicitly supersedes the old diagnostic requirement while
retaining path handling, discovery, Stage 1 and history protections. Old files and
assertions are preserved; replacement tests retain the unchanged cases and move
only the maintenance-specific calls. README and consumer export requirements
explicitly supersede the former legacy-example and Git-archive requirements.

The static fallback warning in the adapter was reviewed: sensor width 36 mm,
AREA/white lights and first plan revision/identifiers are deterministic calibration
defaults. Required direction, measured bounds and identity never fall back. Actual
production plan IDs/revisions are supplied by the existing project documents.

Public schemas were aligned with the external 1.0 boundary. Unsupported fields
(including numeric exposure instructions) are not invented. The closed protocol
carries supplementary labelled production facts in supported text fields.

Focused verification completed: 108 affected tests, 124 adjacent contract/preview/
revision/delivery-resource tests, two subprocess I/O tests, and one new stale-layout
case (235 distinct tests). The final 28-case direction/repair/I/O rerun passed after
binding measurements to blockout hashes. Static validation passed; the documented
fallback warning was reviewed above. The actual consumer-tree README and compiler
entry points ran successfully without approval or Blender execution.

The read-only workspace scan covered 3,782 files with no unread files after Windows
long-path handling. The 178-file consumer tree contains no personal host paths or
maintenance-framework text. Two Blender Scene PNG output fields were replaced with
a relative path; comparison against the original blobs confirms exact field-only,
size-preserving changes. Blender MCP was unavailable, so live reload/render and
external-agent visual judgement remain unresolved. No full regression or formal
acceptance command was run, and no new accepted change record was authored.
