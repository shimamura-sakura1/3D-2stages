# Executable style foundation

Resolve a class and condition with `python runtime/cli.py style-resolve --material painted_metal --condition lightly_weathered`. The result includes the local material library, named resource, resolved shader parameters and environment settings. Regenerate this result after moving machines; it contains local paths. This read-only operation does not modify a project or approve artwork.

`styles/industrial_acg_v1/profile.yaml` version 1.0.0 selects six materials, one overcast lighting setup and camera/color/preview defaults. Conditions are clean, lightly_weathered and weathered. Unknown values and absent Blender resources reject. Semantic YAML and critic guidance support agent judgment; they do not classify intent automatically.

In Blender 4.2+, load `runtime/blender_style_worker.py` using `runpy.run_path`. Use `assign_resolved(object, result)` to apply the selected library resource and condition, `lighting(scene, result['lighting'])` and `render_settings(scene, result['render'], result['color'])` for the environment. The worker is Blender-only; project Python resolves and validates inputs. Calibration uses a new scene and restores the original active scene. Rendering remains an explicit MCP action; a queued job is not a completed image.

The library and calibration blend are executable resources. The preview and raw maintenance outputs live outside the production package in `.deps/v02-phase2/`. Phase 2 does not implement Stage 0–3 project execution or artistic approval.

## Phase 2 validation, 2026-09-14

First run: 8 tests failed for the missing CLI/registry/resources/projection; raw evidence `.deps/v02-phase2/first-failure.txt`. Final focused run: 8 passed. Governance validate has no warnings; declared and runtime contracts passed. Full active regression passed (22 groups). Actual Blender 4.5.13 LTS MCP loaded the named library material, preserved the original three-object scene, and rendered the calibration PNG. Visual inspection found distinct painted coating, reflective metal, granular concrete, dark rubber, transmitting glass and a warm emissive panel. No project or artistic approval was granted.

Resource and image SHA256 at validation:

```json
{
  "styles/industrial_acg_v1/materials/library.blend": "f5e532065d37ef8ad385a8db5af110c294261bb5596741732ace71d874e6ba83",
  "styles/industrial_acg_v1/calibration/calibration.blend": "760c3183e1001fe8a75c9344be3f37d5d342d5cd4cfed270f0802228ae1198e5",
  ".deps/v02-phase2/calibration_preview.png": "39d4c22b9c7abee51807b26c6fe5aad15365f9f59d9eceb63f142795f5c68bd6"
}
```
