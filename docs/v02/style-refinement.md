# Industrial style 1.1.0 refinement

Phase 10 is an explicitly selected refinement of `industrial_acg_v1`. The original
1.0.0 files and default resolver behavior remain the six-material foundation.
Set `style_assignment.profile_version` to `1.1.0` when authoring Stage 0; this
selection is retained through geometry validation, scene preparation and critic
context. Standalone inspection uses `style-resolve --version 1.1.0 --material
painted_metal --condition lightly_weathered`. An unknown version rejects.

Router Step 5 reads this guide for calibration; Step 5V reads it before preparing
separated scene plans. Read the selected `style_signature.yaml` and its scoped
evidence, keep approved geometry intact, then inspect the real calibration and
representative scene renders. `reviewed_by: Codex` and `design_reviewed` identify
design authorship; neither is user artistic approval or an acceptance record.

The refined files live under `styles/industrial_acg_v1/versions/1.1.0`. Its eleven
dimensions have bounded runtime effects:

| Dimension | Consumption |
| --- | --- |
| geometry | Requires preservation of approved geometry; existing operation fingerprints enforce it. |
| surface | Scales material-specific bump distance. |
| palette | Supplies validated per-class RGB values in the slate/teal palette. |
| roughness | Applies a small bounded offset to each material's roughness. |
| weathering | Scales roughness variation before the explicit condition is applied. |
| lighting | Scales key and fill independently for stronger directional daylight. |
| fog | Scales atmospheric density; the scene plan still chooses the fog amount. |
| depth | Requires foreground, midground and background declarations. |
| composition | Bounds explicit camera focal length to the signature's range. |
| emissive | Scales emission strength while keeping restrained warm accents. |
| detail_density | Scales shader noise frequency without changing geometry. |

The supported lighting profile identifier remains `overcast`; its area-light
parameters create directional daylight. This adds no sunset, snow or wet-weather
profiles. The six original material classes remain available and a seventh,
`vegetation`, is accepted only with 1.1.0. Vegetation is a surface class; acquiring
its geometry still requires the ordinary provenance, geometry and review gates.

References have limited authority: the original calibration materials support
material-response comparisons; the original procedural pump render supports
manufactured geometry and material readability; the user's station image is
used only for composition and geometry. None verifies unspecified reference
licenses or provides blanket style authority. The selected nine-category critic
rubric retains subjective severity scores and never supplies automatic approval.

Resources are real Blender libraries with canonical material names
`industrial_acg_v1.<class>`. Repeated calibration temporarily isolates conflicting
live material names while exporting, and restores those names on success or
failure. `StyleRegistry.load(..., require_resources=False)` is only for authoring
the resource definitions; scene preparation and resolution require the resources.
Both YAML and Blender files are hashed in prepared packets. Changing the
signature invalidates an existing packet, while a style-only change leaves the
geometry-derived blockout key unchanged.

Maintenance tests use explicitly labeled Blender/receipt doubles. Real Blender
calibration and scene inspection are separate evidence. HY3D real GPU testing is
suspended at the user's request because of VRAM limits; no synthetic gateway
result is presented as a real GPU result. This change remains pending until the
governance and real-operation gates are completed by the parent maintenance run.
