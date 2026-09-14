# Phase 0 — Freeze Baseline 工作记录

本阶段遵循用户指定的分阶段执行计划，范围仅为冻结现有 v0.1 行为。
正式成功记录由外部框架经 `scripts/govern.py accept` 生成；本文件不代替工具验收。

## Impact Analysis

起点 S4 / change-005，工作树起初干净。新增 `REQ-V02-BASELINE-001`：

- C1：文档默认例实际保持 plan_only、关闭自动审批、拒绝执行/交付而不改变正式状态。
- C2：文档库资产例实际经过拒绝未批准交付、显式测试审核、返工和交付，保留版本及来源。
- C3：文档六类 Contract 指向真实 validator，旧有效 fixture 接受、空文档拒绝。

能力盘点、外部证据范围及 readiness 由维护者逐项核对源码和报告；不宣称自动测试理解了全部文意。
生产 Router 插入点：复用 Step 1 agent 的 Read 增加 `docs/v02/baseline.md`，
明确历史证据与当前状态区别；仍进入原 Step 2，没有另一套生产 Router 或新 tool。

新增测试首次运行 8 个失败，原因全为 baseline.md 缺失。
然后执行 `python scripts/govern.py impact --from SKILL --from workflow-cli`，
direct 为 SKILL/workflow-cli，downstream 为 operator-guide，上游包括契约、状态、路由、
Stage 1/2、SSH/MCP、交付和治理。CLI 只是测试调用/依赖边界，不需要修改其实现。

## Files To Change

- `docs/v02/baseline.md`：能力四态、六类 Contract、可执行示例、历史实机边界及 Gate 0。
- `docs/v02/evidence.json`：非生产、非契约的维护证据，保留输入文档摘要、原回归结果、
  首次失败、代表性操作及未改变的生产文件摘要。
- `docs/v02/phase-0.md`：本记录。
- `tests/test_v02_baseline.py`：新增 8 个用例；旧测试文件不改。
- `SKILL.md`、`interface.json`、`requirements.json`、`tests/manifest.json`：
  Router 读取点、真实 artifact/依赖、独立新需求与测试登记；治理版本 S4 → S5。
- `changes/change-006.json`：仅在工具验收成功后生成。

## Contracts To Add/Modify

不新增或修改生产 Contract，不改 Manifest 数据。治理 requirements/claims 追加，旧记录保持原样。
生产 `schema_version=0.1`、包版本 `0.1.0` 不变。baseline 文档的 JSON 示例只供行为测试执行，
evidence JSON 只作明确标注的非契约维护证据，不引入新 Runtime binding 或生产文件格式。

## Tests To Add

`T-V02-BASELINE` 实际读取 baseline 文档并调用公共 CLI；六类契约使用现有完整 fixture。
命令测试除状态外，比较模型字节、两个版本路径/摘要、来源记录及交付快照。
不会把仅含文件名或关键词的检查当成 claim 已证明。

## Backward Compatibility Risk

本次无生产实现/格式变化，风险限于文档把历史证据误当当前能力、治理登记遗漏和旧测试漂移。
通过限定证据范围、执行历史 active 测试和核对 diff 控制这些风险。
`projects/`、原有 `.deps/` 产物、真实 `.env`、MCP 配置和外部框架均未改动。
新增实际操作仅位于 `.deps/v02-phase0/`，没有把其他任务产物算作本次成果。

## Implemented

完成基线文档及八项行为检查；明确 local-only、回环 HTTP、进程替身、历史实机与未验证范围。
同步治理版本和登记，保留 S4 历史需求/测试，不 supersede 已接受约束。

## Not Implemented

Phase 1–12 均未实施。无 0.2 Schema/迁移、Style System、Route D、LookDev 拆分、
Preview metadata、Visual Critic 或 Revision Loop，也未建立空壳模块。

## Tests Executed

- 实施前 validate：pass，warnings=[]。
- 实施前 contract-test：declared_contract=pass、runtime_contract=pass。
- 实施前 test：首次受沙箱回环端口限制失败；相同源码在沙箱外重跑 18/18 组通过。
  原 pytest 组共 160 项通过，另有 CLI characterization 和 runtime I/O 测试；不把组数当用例数。
- 新测试首次 8 failed（文档尚未实现）；实现文档后 8 passed。
- 最终 validate：pass，warnings=[]；无需要人工消解的静态 warning。
- 最终 contract-test：declared_contract=pass、runtime_contract=pass。
- 最终 `test --requirement REQ-V02-BASELINE-001`：19/19 active 组通过，
  包括全部 18 组历史测试与新增 8 个用例。既有 pytest 160 项加新增 8 项，
  另有 CLI characterization 与运行契约证据。
- 正式 accept 再执行全部 gate；其结果、版本链和完整证据只以工具 change record 为准。

原始日志位于 `.skillctl/reports/`、`.deps/v02-phase0/test-first.txt`；
共享摘要和 SHA256 位于 [evidence.json](evidence.json)，首次失败不被通过结果覆盖。

## Real External Validation Executed

本次没有新 SSH、GPU、Blender MCP/batch 渲染或 Windows 实机验证。
按原 Router 在 `.deps/v02-phase0/` 的新隔离目录实际执行两个文档示例：
默认规划与拒绝门禁；CC0 长椅检索 → A 获取 → 待审核 → 拒绝交付 → 测试返工审核 →
rev01 → 拒绝交付 → 合成批准 → 资产交付。保存全部项目文件和摘要。
已验证 rev00/rev01 都保留且来源一致，资产项目最终 complete，auto_approve=false，
Stage 2 仍 not_started。这是本地真实文件操作和测试审核输入，不是生产资产艺术验收。

## Known Limitations

完整远程 Stage 1、用户输入与生成结果许可、Windows 实机、艺术质量仍未验证。
旧 Blender 安装报告中的历史缺陷与 S4 修复已区分。本次不重新证明外部服务当前在线。
单一材质/固定参数是源码观察，不是本次新增画面的视觉评价。
测试不自动证明整篇基线的语义正确性，能力表由维护者审查。

## Next Phase Readiness

`Next Phase Readiness = READY`：Gate 0 的回归记录、能力边界、baseline 文档均已完成，
新增断言与历史回归通过，实际本地代表性操作完成。人工语义审查确认没有把远程 smoke、
替身、准备操作包或技术文件有效性当成完整外部流程或美术批准。
44 个生产文件的摘要不变，8 条原需求及18条原测试登记与 S4 快照完全一致。
S5 正式接受仍以工具生成的 `changes/change-006.json` 为准；不存在该成功记录就不能声称已接受。
READY 仅表示可进入 Phase 1 的契约设计，不表示 v0.2 已完成。
按用户“一步一步来”的要求，本次交付停在 Phase 0 边界。
