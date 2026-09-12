# Blender builder

Read the approved inputs and shared style bible. Build a contract-valid plan with explicit meter-based dimensions, XYZ locations, XYZ Euler rotations in degrees, and positive scale factors. Camera focal length is in millimeters. `railway` dimensions mean length, gauge and rail height; count means sleepers. `box` dimensions mean width, depth and height.

Run Stage 2 preflight. Required assets must appear in the plan unless partial mode is explicitly enabled. A listed unapproved or missing asset is never a placeholder. Use a procedural box if the user approved a placeholder.

Default to Codex Blender MCP. Obtain the runtime's `mcp_calls.json`, call the addon status tool, then invoke `execute_blender_code` with each prepared step in order. Use the actual user prompt in `user_prompt`. These commands require that Blender can access the same local project paths. Do not mark a prepared or queued job complete. After render is queued, inspect its status and files before calling `stage2-complete`; never repeat assembly/export/render after an ambiguous timeout. Request a new job if inputs changed, preserving the previous artifacts for diagnosis.

The worker creates a new scene, exports that scene alone, and does not clear existing user scenes or save over the currently opened file. Do not replace it with a scene-clearing script. Batch execution is an explicit alternative (`--backend batch`), not an automatic fallback when MCP is disconnected.

The fixed worker imports embedded GLB or geometry-only OBJ, removes imported lights/cameras, groups parts, centers the base, applies placement, builds boxes/railway structures, sets a shared procedural material, camera and sun, packs the scene, and exports a preview plus BLEND/GLB. It preserves imported material styles; artistic shader unification and topology repair require later tooling. Reject plans requiring unsupported operations rather than substituting unrelated geometry.

Use the preview for final review of composition, dimensions, materials, geometry cost and attribution. A dry run only validates inputs. A successful process must still produce and validate the expected outputs before recording a build.
