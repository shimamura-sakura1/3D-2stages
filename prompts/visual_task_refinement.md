# Refine a visual direction

Use the task's previous direction, matching review, current inputs and scene observations. If an image is supplied, view that exact image. Change only reviewed sections and retain successful decisions, caller constraints and preserve rules. Return one direction whose parent is the previous direction ID and whose revision is strictly greater. A new direction ID and revision gaps are valid.

Respect the production action limits supplied in camera/lighting constraints. Camera small/medium angular and focal changes are at most 5/10 degrees or mm, coverage changes .05/.1; light angles 5/10 degrees and fill ratio .1/.2. Fog changes use the explicitly selected adjacent execution levels. Do not change geometry, materials, target mode, or unsupported composition controls. If the review needs those changes, report a concrete planning issue instead.

Return explicit execution choices with rationale. Submit a candidate; main applies the existing revision plan only after checking real old/new differences, the current image, user authorization and remaining preview budget.
