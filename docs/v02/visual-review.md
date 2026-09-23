# Current-preview visual review

`review-context PROJECT` validates the current successful metadata, actual PNG, current Stage 0 and separated scene plans and returns an inspection context without changing state. It includes the nine-category style rubric, image path/hash and current manifest version. It does not generate an artistic diagnosis.

Codex views that exact image, follows `prompts/render_critic.md`, and authors the existing visual_review contract. Scores consistently mean problem severity, from 0 (no visible problem) to 1 (severe). The review must reference the current scene, metadata and image and use the next immutable revision.

`visual-review-submit PROJECT --review REVIEW.json --expected-version N` writes only through ManifestManager. The current pending preview can advance to visual_revision or final_review_required. Neither grants final approval; no Blender or model call runs. Legacy and plan_only projects cannot use this execution boundary.

Current artifact hashes, actual image bytes/PNG dimensions, metadata/render-plan links, object/action scopes, version and revision are rechecked under the manifest lock. Old images, failed renders, malformed reviews and changed inputs reject without official writes. Historical operation packets intentionally become stale after preview completion; review validates the current formal documents directly instead of replaying that packet.

Diagnosis and persistence are separate from bounded execution. A suggested geometry or base-material change is a review need, never a reason to bypass the existing geometry and visual approval records.

使用外部视觉导演时，参阅 [Render Director 接入](render-director.md)。

## Visual task review

For the current task direction, prepare review_render; runtime binds its exact completed PNG and prior direction. Main views that PNG and authors findings, successful decisions, four recommended-change groups and preserve constraints. Submit this candidate, then `visual-review-submit PROJECT --review REVIEW --visual-task ID --expected-version N` with the independently authored nine-category production review. No automatic severity-to-score conversion occurs. Four empty groups do not request revision. Image/direction mismatch or stale inputs reject without changing formal state. See [task tracking](task-tracking.md).
