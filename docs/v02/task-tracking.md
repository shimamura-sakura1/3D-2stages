# Visual tasks and recovery

Main owns planning, visual decisions, scheduling and continuous progress. Runtime snapshots inputs and validates decisions; it never performs artistic reasoning. The operations are `create_direction`, `review_render`, `refine_direction`. Task folders are production-generated `stage2/visual_tasks/<task_id>/`; do not invent task IDs or copy a result into another task.

Prepare with `python -m runtime.cli visual-task-prepare PROJECT --request SPEC --expected-version N`. SPEC contains `operation`; creation also contains measured `scene_context` and authored `plans`. Optional `reference_ids` chooses traceable PNG references. Start with `visual-task-start PROJECT --task-id ID --expected-version N`, read the task request and the matching local prompt, then author its direction or review. Submit with `visual-task-submit PROJECT --task-id ID --decision JSON --expected-version N`; direction tasks also supply `--execution JSON` containing `softness` (`small`, `medium`, `large`), `fog_amount` (`none`, `subtle`, `medium`, `dense`) and a concrete `reason`. Runtime does not guess these choices from prose.

Use `visual-task-status PROJECT --task-id ID` before dispatch and after interruptions. Recovery follows this order:

1. `accepted`: continue the downstream Router step; do not consume the result again.
2. `result_available`, or a published external output: validate and collect first, then submit the corresponding production operation.
3. `running` with reliable current execution evidence: wait/query. The label alone is not evidence that a worker is alive.
4. `prepared`, or a confirmed ended attempt: start once under existing authorization. Record a confirmed interruption with `visual-task-interrupt ... --reason TEXT --expected-version N`; retries are bounded to three task attempts.
5. Unknown execution status: inspect the selected caller/helper evidence. Do not mark interrupted just to start again.

Input changes require a new task and leave the old record intact. Manifest versions created by task preparation/progress do not themselves change the input baseline; production documents, approvals, geometry, selected Style resources and image bytes do. All writes still require the current expected_version.

Candidate submission is not production acceptance. `scene-plans-submit --visual-task ID`, `visual-review-submit --visual-task ID`, and `revision-apply --visual-task ID` validate the candidate and adopt it atomically with their respective production changes. A rejected adoption leaves formal state unchanged. The legacy direction parameters are mutually exclusive. Main reports completed work, current operation, blockers and next action; task status never substitutes for approval or real render receipts.

Task attempts do not reset the existing total preview budget. The [preview job/receipt rules](preview.md) govern rendering; task recovery must not reserve another pass merely because the conversation restarted.
