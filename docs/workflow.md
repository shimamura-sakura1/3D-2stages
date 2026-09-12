# Production operator procedure

SKILL.md owns the Execution Router. This document supplies its operator details, not a second execution engine.

Preserve artistic intent and record material assumptions. Use prompts/parent.md and prompts/asset_planner.md as planning advice. The agent supplies refined briefs, tasks and Blender plans; Python does not interpret natural-language intent. Prefer procedural geometry for rails, platforms and repeated structures.

Choose the user-requested mode explicitly. The formal CLI default is plan_only. Show the refined brief before expensive generation unless execution was already authorized. Templates are starting points, not inferred requirements. Official state changes go through runtime/cli.py and ManifestManager.

Search all configured libraries before Stage 1 routing. Candidate scores and rights come from evidence. The router applies declared numeric policy; provider failure never means no assets exist. Review actual assets before approval unless auto_approve was explicitly enabled. review.required=false does not grant approval. Rework is per asset, bounded, and preserves prior outputs.

Keep Blender MCP as the default. Follow docs/mcp_and_ssh.md and prompts/blender_builder.md. A prepared packet or queued render is not a build. Execute the fixed steps through available Codex MCP tools with the actual user prompt; then check files using stage2-complete. Do not silently switch to batch or clear existing scenes. Partial scenes require the user's choice. Final scene review precedes delivery.

HY3D belongs on a remote GPU server through configs/hy3d_ssh.yaml. No server is provisioned yet. Inspect hardware and deploy a compatible gateway after connection details exist. Keep credentials out of manifests. Offline tests do not prove remote inference, live Blender rendering, or artistic judgment.

The following executable documentation example establishes only command behavior. PROJECT is replaced with a fresh temporary directory. Argument arrays are passed directly, never executed as shell text.

```json
[
  {"argv": ["init", "PROJECT", "--id", "documented_example", "--brief", "A quiet station"], "exit": 0, "field": "mode", "equals": "plan_only"},
  {"argv": ["run", "PROJECT"], "exit": 0, "field": "status", "equals": "plan_only"},
  {"argv": ["stage2", "PROJECT", "--dry-run"], "exit": 2, "field": "error", "contains": "Cannot read"}
]
```

The final rejection above is a missing plan, not proof of the mode gate by itself. Separate stage-boundary tests check that gate with a present plan.
