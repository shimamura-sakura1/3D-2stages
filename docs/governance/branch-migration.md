# Branch and developer-host migration

The user authorized consolidating the repository into `main` (consumer Skill) and
`dev/v3` (complete development source), preserving history and running only tests
affected by this work. No full regression or new formal acceptance is claimed.

The previous complete local source was cd733f9; it was published on dev/v3 before
branch cleanup. Main received a normal descendant commit with the exact consumer
tree from 9fc7b6a, preserving the previous main history. Old branch tips are retained
as archive/2026-09-19 tags before deleting obsolete branch names.

Development instructions now use configurable host paths, Git LFS, independent
Python environments and explicit external dependency revisions. The compatible
Render Director revision is c6f16c9bd17f043a4f5c46091b7f3fdbc7da355a; its three public
schemas match this Skill. The later external file-task interface is incompatible
and is rejected by host setup rather than silently treated as usable.

The new setup and release scripts are development utilities, outside the production
Execution Router. They are registered as advisory artifacts; the new maintenance
requirement remains unresolved for formal governance purposes. Tests verify the
implemented utility behavior; they do not turn these scripts into production
runtime bindings or establish full Skill acceptance. No production Router step or
historical accepted requirement/test assertion was changed.

Test-first evidence: six host/setup/export tests failed before their helper and
documentation existed; four release tests failed before the release helper existed.
The tests subsequently passed. The additional external-schema mismatch test verifies
that an incompatible checkout cannot overwrite local settings.

The developer source scan found no private keys or service tokens. Real personal
paths found in accepted history and historical development notes were already
present as identical Git blobs on the same remote. They remain immutable historical
evidence. Current host setup instructions were made portable; local .env and .deps
were not committed or included in the consumer tree.

Detailed local command output is retained under .skillctl/reports. Live Windows
setup verification is distinct from fixture-based branch/write rejection tests;
this work does not claim a macOS host run or external-agent rendering validation.

Focused verification passed 42 tests across developer setup, release preparation,
consumer distribution and existing runtime portability. Static validation passed
with the pre-existing render-direction calibration-default warning; this iteration
does not change that adapter. The real Windows setup command saved local settings
and successfully rechecked Blender version, development dependencies and the pinned
external checkout. No new successful changes record was written.
